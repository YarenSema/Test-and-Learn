"""
internet.py — sohbet icin hizli internet aramasi
------------------------------------------------
Neden boyle:
  * Gemini'nin kendi "Google Search" araci ucretsiz API anahtarinda kota
    hatasi (429) veriyor.
  * `ddgs` paketinin motorlari (bing/yandex/duckduckgo/brave) kurum agindan
    cogunlukla "No results found" donuyor (Kasim 2026 olcumu: 6 motordan
    5'i bos). Tek basina guvenilir degil.
  * Google News RSS ve Bing RSS ise anahtar istemiyor, 1 saniyenin altinda
    ve tarihli sonuc donuyor. Chrome/tarayici gerektirmez, Streamlit
    Cloud'da da calisir.

Bu yuzden butun kaynaklara AYNI ANDA sorulur, sonuclar birlestirilir,
tekrarlar atilir, soruyla alakasizlar elenir ve haberler tarihe gore
siralanir. ddgs yalnizca ek kaynak olarak (calisirsa) kullanilir.

Arama asla sohbeti bozamaz: her hata yutulur, en kotu ihtimalle bos liste
doner ve asistan internet olmadan yanit verir.
"""
import html
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

try:                       # Windows'ta kurum sertifikalari (proxy) icin
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

ZAMAN_ASIMI = 6.0          # saniye: toplam bekleme ust siniri
SONUC_SAYISI = 8           # modele giden en fazla sonuc
OZET_UZUNLUGU = 400        # sonuc basina modele giden karakter
ONBELLEK_SN = 600          # ayni sorgu 10 dk icinde tekrar aranmaz
HABER_GUN = 45             # "guncel" sorularda bu kadar gunden eski haber atilir

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/130.0 Safari/537.36",
       "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.6"}

_havuz = ThreadPoolExecutor(max_workers=16, thread_name_prefix="arama")
_onbellek = {}
_kilit = threading.Lock()


# --- Sorgu hazirlama -------------------------------------------------------
# Arama motoruna sohbet cumlesi degil anahtar kelime gitmeli:
# "selam bana internetten ... bulabilir misin" -> "kasım marketing kampanya
# optimizasyonları". Kelimeler sadelestirilmis (ç->c, ı->i ...) halde.
_DOLGU = {
    "selam", "merhaba", "bana", "bize", "bizi", "biz", "benim", "bizim",
    "lutfen", "canim", "internet", "internetten", "internette", "webden",
    "veri", "veriler", "verilerimiz", "verilerimizden", "verilerden",
    "verilerimizi", "havuz", "havuzdan", "yararlanarak", "kullanarak",
    "faydalanarak", "bakarak", "bulabilir", "bulur", "bulabilirmisin",
    "misin", "musun", "misiniz", "musunuz", "olur", "acaba", "ozel",
    "ilgili", "hakkinda", "konusunda", "uzerine", "alakali", "neler",
    "nedir", "haber", "haberler", "haberleri", "haberlerini", "guncel",
    "guncellemeler", "son", "yeni", "gelismeler", "gelismeleri", "ayi",
    "ayinda", "donemi", "doneminde", "sektor", "sektorumuz",
    "sektorumuze", "sektorumuzde", "sektorumuzun", "sektorel", "ve",
    "ile", "icin", "bir", "bu", "en", "cok", "daha", "gibi", "ne", "nasil",
    "hangi", "ver", "verir", "goster", "anlat", "yaz", "ozetle", "listele",
    "arastir", "arastirir", "bul", "nedir", "yarar", "isimize", "artiririm",
    "arttiririm", "yapabilirim", "yapmaliyim", "edebilirim", "olmali",
}
# Turkce haberlerde Ingilizce terim yerine Turkcesi geciyor; aramada ve
# alaka puaninda Turkcesi kullanilir. (sadelestirilmis kok -> Turkce terim)
_ESANLAMLI = {
    "marketing": "pazarlama",
    "advertising": "reklam",
    "ecommerce": "e-ticaret",
    "campaign": "kampanya",
}
# Bu kelimelerden biri varsa soru pazarlama/reklam konulu sayilir
_PAZARLAMA_DESENI = re.compile(r"kampanya|reklam|pazarlama|marketing|meta|"
                               r"google|tiktok|roas|cpc|cpa|ctr|donusum|"
                               r"e-?ticaret|performans|kreatif|medya")
# Bu kelimelerden biri varsa "guncel haber" istenmis sayilir
_HABER_DESENI = re.compile(r"haber|guncel|son gelisme|bu ay|bu hafta|yeni "
                           r"cik|duyur|news|trend")
# "Bizim sektor" denince aramaya eklenen baglam
SEKTOR_TERIMLERI = ("banyo", "yapı malzemesi")


def _sade(metin):
    esle = str.maketrans("çğıöşüâîûÇĞİÖŞÜ", "cgiosuaiuCGIOSU")
    return str(metin).translate(esle).lower()


def _anahtar_kelimeler(soru):
    """Sorudaki anlamli kelimeler (orijinal yazimla, sirasi korunur)."""
    kelimeler = re.findall(r"[\wçğıöşüÇĞİÖŞÜâîû'’+-]+", soru or "")
    secilen, gorulen = [], set()
    for k in kelimeler:
        k = k.split("'")[0].split("’")[0].strip("-")
        kok = _sade(k)
        # AI, SEO, CTV, ROAS gibi kisaltmalar kisa olsa da anlamlidir
        kisaltma = k.isupper() and len(k) >= 2
        if not kisaltma and (len(kok) < 3 or kok in _DOLGU
                             or (kok.isdigit() and len(kok) < 4)):
            continue
        k = _ESANLAMLI.get(kok, k)
        if _sade(k) not in gorulen:
            gorulen.add(_sade(k))
            secilen.append(k)
    return secilen


def _kok(kelime):
    """Alaka kontrolu icin kaba Turkce kok: ekleri tolere etmek icin kirpar."""
    sade = _sade(kelime)
    if len(sade) <= 5:
        return sade
    return sade[:6] if len(sade) >= 8 else sade[:5]


def sorgulari_hazirla(soru):
    """
    (sorgular, haber_mi) doner. Ilk sorgu cekirdek anahtar kelimeler,
    sonrakiler kisaltilmis / konu ve sektor baglamli varyantlar.
    """
    sade = _sade(soru)
    haber = bool(_HABER_DESENI.search(sade))
    kelimeler = _anahtar_kelimeler(soru)
    if not kelimeler:
        return [], haber
    sorgular = [" ".join(kelimeler[:6])]
    if len(kelimeler) > 3:
        sorgular.append(" ".join(kelimeler[:3]))
    pazarlama = bool(_PAZARLAMA_DESENI.search(sade))
    ilk = kelimeler[0]
    if pazarlama and not re.search(r"pazarlama|reklam", _sade(sorgular[-1])):
        # Haber sitelerinde "dijital pazarlama"/"reklam" gecen yazilar
        sorgular.append(f"{ilk} dijital pazarlama")
    if re.search(r"sektor|bizim|vitra|banyo|eczacibasi", sade):
        sorgular.append(f"{SEKTOR_TERIMLERI[0]} sektörü {ilk}"
                        + (" pazarlama" if pazarlama else ""))
    # tekrarlari at, sirayi koru
    return list(dict.fromkeys(sorgular)), haber


# --- Gemini ile arama planlama ---------------------------------------------
# Kelime ayiklamak icgoru sorularinda ise yaramiyor: "Rakiplerimiz bu ay ne
# yapiyor?" -> "Rakiplerimiz yapiyor" aramasi dizi/futbol sonucu getiriyor.
# Bu yuzden sorgulari model yazar; bu metin o istemdir. Model cevap
# veremezse uygulama yukaridaki kelime yontemine geri doner.
SIRKET_BAGLAMI = (
    "Kullanıcı Eczacıbaşı Yapı Ürünleri'nin (markalar: VitrA, Artema, "
    "Intema, VitrA Karo) dijital pazarlama ekibinde. Sektör: banyo, "
    "vitrifiye/seramik sağlıklı yapı ürünleri, armatür/batarya, karo, banyo "
    "mobilyası. Kanallar: D2C e-ticaret sitesi, Hepsiburada, Trendyol, "
    "bayi ve showroom. Reklam platformları: Meta, Google (Search, PMax, "
    "Demand Gen, AI Max, YouTube), TikTok. Global rakipler: Hansgrohe, "
    "GROHE, Kohler, Geberit, Duravit, Villeroy & Boch, Ideal Standard, "
    "Roca, TOTO, Moen. Türkiye rakipleri: Kale (Kalebodur), Creavit, "
    "Seramiksan, Turkuaz Seramik, Ece Banyo, Bien.")

PLAN_ISTEMI = """Sen bir pazarlama araştırma asistanının ARAMA PLANLAYICISISIN.
{baglam}
Bugünün tarihi: {bugun}.

Görev: Kullanıcının sorusuna güncel, zengin arka plan bilgisi getirecek 3-5 web arama sorgusu yaz.
Kurallar:
- Sorgular arama motoruna yazılacak 2-6 kelimelik anahtar kelime öbekleri olsun, cümle değil.
- "rakiplerimiz", "sektörümüz", "markamız" gibi ifadeleri somut marka / sektör / platform adlarına çevir.
- Şirket içi kelimeleri ("verilerimiz", "testlerimiz", "havuz", "içgörü", "kampanyalarımız") sorguya KOYMA; bunların konusunu (ör. Meta reklam kreatif stratejisi) ara.
- Kendi markalarımızın (VitrA, Artema, Intema) resmi sitesini veya pazaryeri mağaza sayfasını getirecek sorgular yazma; kullanıcı onları zaten biliyor. Marka adını ancak haber, basın ya da rakip karşılaştırması aranıyorsa kullan. Odak: sektör haberleri, rakip hamleleri, platform güncellemeleri, benchmark ve vaka çalışmaları.
- En az bir Türkçe ve en az bir İngilizce sorgu yaz (platform güncellemeleri ve global rakipler İngilizcede daha zengin).
- Güncellik gereken konularda ay/yıl ekle (ör. "Kasım 2026").
- Soru yalnızca şirket içi bir kaydı istiyorsa (ör. "REAL003'ü özetle", "aktif testleri listele", "bu dosyayı tabloya çevir") ve dış bilgi değer katmıyorsa ara=false ver. İçgörü, strateji, öneri, trend, rakip, benchmark, sektör sorularında ara=true ver.
{onceki}Kullanıcının sorusu: {soru}

Yalnızca JSON döndür: {{"ara": true, "sorgular": ["...", "..."]}}"""


def plan_istemi(soru, onceki_soru=""):
    """Gemini'ye gonderilecek arama planlama istemi."""
    return PLAN_ISTEMI.format(
        baglam=SIRKET_BAGLAMI,
        bugun=datetime.now().strftime("%d.%m.%Y"),
        onceki=(f"Önceki soru (bağlam için): {onceki_soru[:300]}\n"
                if onceki_soru else ""),
        soru=(soru or "")[:1000])


def plani_coz(metin):
    """Model yanitindan (ara_mi, [sorgular]) cikarir; okunamazsa None."""
    import json
    eslesme = re.search(r"\{.*\}", metin or "", re.S)
    if not eslesme:
        return None
    try:
        veri = json.loads(eslesme.group(0))
    except Exception:
        return None
    sorgular = [" ".join(str(s).split())[:120]
                for s in (veri.get("sorgular") or []) if str(s).strip()]
    ara_mi = bool(veri.get("ara", bool(sorgular)))
    if ara_mi and not sorgular:
        return None
    return ara_mi, sorgular[:5]


# --- Kaynaklar -------------------------------------------------------------
def _getir(url, zaman_asimi):
    istek = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
        return yanit.read()


def _tarih(metin):
    try:
        t = parsedate_to_datetime(metin)
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _html_temizle(metin):
    metin = re.sub(r"<[^>]+>", " ", html.unescape(metin or ""))
    return " ".join(metin.split())


def _rss(url, tur, zaman_asimi, adet=8):
    """RSS beslemesini [{baslik, url, ozet, kaynak, tarih, tur}] yapar."""
    kok = ET.fromstring(_getir(url, zaman_asimi))
    sonuclar = []
    for oge in kok.findall(".//item")[:adet]:
        baslik = _html_temizle(oge.findtext("title"))
        link = (oge.findtext("link") or "").strip()
        kaynak_ogesi = oge.find("source")
        kaynak = (kaynak_ogesi.text or "").strip() if kaynak_ogesi is not None else ""
        # Google News basligin sonuna " - Yayinci" ekler
        if kaynak and baslik.endswith(" - " + kaynak):
            baslik = baslik[: -len(kaynak) - 3]
        # Bing haber linkleri yonlendirme; gercek adres url= parametresinde
        if "bing.com/news/apiclick" in link:
            gercek = urllib.parse.parse_qs(
                urllib.parse.urlparse(link).query).get("url")
            if gercek:
                link = gercek[0]
        if not kaynak:
            kaynak = urllib.parse.urlparse(link).netloc.removeprefix("www.")
        sonuclar.append({
            "baslik": baslik or link, "url": link,
            "ozet": _html_temizle(oge.findtext("description"))[:OZET_UZUNLUGU],
            "kaynak": kaynak, "tarih": _tarih(oge.findtext("pubDate")),
            "tur": tur,
        })
    return sonuclar


def _google_haber(sorgu, zaman_asimi, gun=None):
    q = sorgu + (f" when:{gun}d" if gun else "")
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
           + "&hl=tr&gl=TR&ceid=TR:tr")
    return _rss(url, "haber", zaman_asimi)


def _bing_haber(sorgu, zaman_asimi):
    url = ("https://www.bing.com/news/search?q=" + urllib.parse.quote(sorgu)
           + "&format=rss&setlang=tr&cc=TR")
    return _rss(url, "haber", zaman_asimi)


def _bing_web(sorgu, zaman_asimi):
    url = ("https://www.bing.com/search?q=" + urllib.parse.quote(sorgu)
           + "&format=rss&setlang=tr&cc=TR")
    sonuclar = _rss(url, "web", zaman_asimi)
    for s in sonuclar:          # web sonucunda pubDate "tarama tarihi"dir
        s["tarih"] = None
    return sonuclar


def _ddgs(sorgu, zaman_asimi):
    from ddgs import DDGS
    ham = DDGS(timeout=int(zaman_asimi)).text(
        sorgu, region="tr-tr", max_results=6, backend="auto")
    return [{"baslik": (r.get("title") or "").strip(),
             "url": (r.get("href") or "").strip(),
             "ozet": (r.get("body") or "").strip()[:OZET_UZUNLUGU],
             "kaynak": urllib.parse.urlparse(r.get("href") or "")
                                   .netloc.removeprefix("www."),
             "tarih": None, "tur": "web"} for r in ham or []]


# --- Birlestirme ----------------------------------------------------------
# "kampanya", "indirim", "marka" bilerek yok: market/indirim haberlerinde de
# geciyor, pazarlama yazisini ayirt etmiyor.
_PAZARLAMA_KELIMELERI = ("pazarlama", "reklam", "marketing", "e-ticaret",
                         "eticaret", "dijital", "tuketici davran", "medya",
                         "influencer", "yapay zeka", "performans", "ajans")


def _puan(sonuc, kokler, pazarlama):
    """Kac anahtar kelime geciyor (+ pazarlama baglami varsa +1)."""
    metin = " " + _sade(sonuc["baslik"] + " " + sonuc["ozet"]) + " "
    # kelime BASINDA eslesme: "market" kokunun "supermarket"te
    # eslesmemesi icin
    puan = sum(1 for k in kokler if re.search(r"[^a-z0-9]" + re.escape(k),
                                              metin))
    if pazarlama and any(p in metin for p in _PAZARLAMA_KELIMELERI):
        puan += 1
    return puan


def _ana_sayfa_mi(url):
    """meta.com, facebook.com/ gibi site ana sayfalari bilgi tasimaz."""
    yol = urllib.parse.urlparse(url).path.strip("/")
    return yol == "" or yol.lower() in {"tr", "en", "tr-tr", "en-us",
                                        "index.html", "home"}


def _birlestir(gruplar, kelimeler, haber, adet, pazarlama=False,
               planli=False):
    gorulen, adaylar = set(), []
    simdi = datetime.now(timezone.utc)
    kokler = list(dict.fromkeys(_kok(k) for k in kelimeler))
    for oncelik, grup in enumerate(gruplar):
        for s in grup:
            if not s["url"].lower().startswith(("http://", "https://")):
                continue
            if s["tur"] == "web" and _ana_sayfa_mi(s["url"]):
                continue
            anahtar = _sade(re.sub(r"\W+", "", s["baslik"]))[:60]
            if anahtar in gorulen or s["url"] in gorulen:
                continue
            if (haber and s["tarih"]
                    and (simdi - s["tarih"]).days > HABER_GUN):
                continue
            gorulen.update({anahtar, s["url"]})
            adaylar.append((_puan(s, kokler, pazarlama), oncelik, s))

    if not adaylar:
        return []
    # Esik: en az 2 eslesme (tek kelimelik soruda 1). Kelime yonteminde
    # yeterli sonuc kalmazsa esik gevsetilir; planli sorgularda gevsetilmez
    # (az ama dolu sonuc, cok ama bos sonuctan iyidir — sayfalar okunuyor).
    esik = 2 if len(kokler) + pazarlama >= 2 else 1
    secilen = [a for a in adaylar if a[0] >= esik]
    if len(secilen) < 3 and not (planli and secilen):
        secilen = [a for a in adaylar if a[0] >= 1]

    # Guncel haber isteniyorsa: once haberler, puan, sonra yeniden eskiye.
    def sira(a):
        puan, oncelik, s = a
        zaman = s["tarih"].timestamp() if s["tarih"] else 0
        if haber:
            return (0 if s["tur"] == "haber" else 1, -puan, -zaman)
        return (-puan, oncelik, -zaman)
    secilen.sort(key=sira)
    sonuclar = [s for _, _, s in secilen]
    if not haber:
        # Haber ve web'i dengeli karistir (ikisi de varsa)
        haberler = [s for s in sonuclar if s["tur"] == "haber"]
        web = [s for s in sonuclar if s["tur"] != "haber"]
        karisik = []
        while haberler or web:
            for liste in (haberler, web):
                if liste:
                    karisik.append(liste.pop(0))
        sonuclar = karisik
    return sonuclar[:adet]


def ara(soru, adet=SONUC_SAYISI, zaman_asimi=ZAMAN_ASIMI, sorgular=None):
    """
    Tum kaynaklarda paralel arar.
    sorgular verilirse (orn. Gemini'nin planladigi sorgular) onlar kullanilir;
    verilmezse sorudan anahtar kelime cikarilir (yedek yontem).
    [{baslik, url, ozet, kaynak, tarih, tur}] doner; sorun olursa bos liste.
    Bos sonuc onbellege alinmaz (tekrar denemede yeniden aransin).
    """
    if sorgular:
        sorgular = list(dict.fromkeys(
            " ".join(str(s).split()) for s in sorgular if str(s).strip()))[:5]
        haber = bool(_HABER_DESENI.search(_sade(soru)))
        kelimeler = _anahtar_kelimeler(" ".join(sorgular))
        planli = True
    else:
        sorgular, haber = sorgulari_hazirla(soru)
        kelimeler = _anahtar_kelimeler(soru)
        planli = False
    if not sorgular:
        return []

    anahtar = (tuple(sorgular), haber, adet)
    with _kilit:
        kayit = _onbellek.get(anahtar)
        if kayit and time.time() - kayit[0] < ONBELLEK_SN:
            return kayit[1]

    gun = 30 if haber else None
    sure = max(1.0, zaman_asimi - 0.5)
    isler = []
    for i, sorgu in enumerate(sorgular):
        isler.append(_havuz.submit(_google_haber, sorgu, sure, gun))
        isler.append(_havuz.submit(_bing_haber, sorgu, sure))
        # Planli sorgular zaten iyi; hepsinde web de aranir. Yedek yontemde
        # web aramasi yalnizca cekirdek sorguda yapilir.
        if planli or i == 0:
            isler.append(_havuz.submit(_bing_web, sorgu, sure))
        if i == 0:
            isler.append(_havuz.submit(_ddgs, sorgu, sure))

    bitti, _ = wait(isler, timeout=zaman_asimi)
    gruplar = []
    for is_ in isler:                      # sorgu onceligi korunsun
        if is_ in bitti:
            try:
                gruplar.append(is_.result() or [])
            except Exception:
                continue                   # bu kaynak sonuc vermedi

    pazarlama = bool(_PAZARLAMA_DESENI.search(
        _sade(soru + " " + " ".join(sorgular))))
    sonuclar = _birlestir(gruplar, kelimeler, haber, adet, pazarlama,
                          planli)
    if sonuclar:
        with _kilit:
            _onbellek[anahtar] = (time.time(), sonuclar)
    return sonuclar


# --- Sayfa okuma (derinlik) ----------------------------------------------
# Arama sonuclari yalnizca baslik + 1-2 cumle verir; asistanin "arka plani
# dolu" yanit verebilmesi icin en iyi sayfalarin ICINDEN soruyla ilgili
# paragraflar alinir.
OKUNACAK_SAYFA = 5
SAYFA_KARAKTER = 1800      # sayfa basina modele giden icerik
SAYFA_ZAMAN_ASIMI = 6.0
# Icerigi okunamayan / giris isteyen / yonlendirme yapan siteler
_OKUNMAZ = ("news.google.com", "youtube.com", "instagram.com",
            "facebook.com", "x.com", "twitter.com", "linkedin.com",
            "tiktok.com", "books.google.", "pinterest.")


def _sayfa_paragraflari(url, zaman_asimi):
    istek = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
        tur = yanit.headers.get_content_type() or ""
        if "html" not in tur:
            return []                      # PDF, resim vb. atlanir
        kodlama = yanit.headers.get_content_charset() or "utf-8"
        ham = yanit.read(2_000_000)
    metin = ham.decode(kodlama, errors="replace")
    metin = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header|"
                   r"aside|form|button)\b[^>]*>.*?</\1>", " ", metin)
    parcalar = re.findall(r"(?is)<(p|li|h2|h3|blockquote)\b[^>]*>(.*?)</\1>",
                          metin)
    paragraflar = []
    for _, icerik in parcalar:
        p = _html_temizle(icerik)
        if len(p) >= 60 and p not in paragraflar:
            paragraflar.append(p)
    return paragraflar


def _ilgili_icerik(paragraflar, kokler):
    """Soruyla en cok eslesen paragraflari, sayfadaki sirasiyla secer."""
    puanli = []
    for sira, p in enumerate(paragraflar):
        sade = " " + _sade(p) + " "
        puan = sum(1 for k in kokler
                   if re.search(r"[^a-z0-9]" + re.escape(k), sade))
        puanli.append((puan, sira, p))
    # Eslesme yoksa sayfanin girisi (ilk paragraflar) kullanilir
    secim = sorted(puanli, key=lambda x: (-x[0], x[1]))
    secilen, toplam = [], 0
    for puan, sira, p in secim:
        if toplam >= SAYFA_KARAKTER:
            break
        secilen.append((sira, p[:700]))
        toplam += min(len(p), 700)
    return " … ".join(p for _, p in sorted(secilen))[:SAYFA_KARAKTER]


def sayfalari_oku(sonuclar, anahtar_metin, adet=OKUNACAK_SAYFA,
                  zaman_asimi=SAYFA_ZAMAN_ASIMI):
    """
    En ustteki okunabilir sonuclarin sayfalarini paralel indirir ve her
    sonuca 'icerik' alani ekler. Okunan sayfa sayisini doner.
    """
    kokler = list(dict.fromkeys(
        _kok(k) for k in _anahtar_kelimeler(anahtar_metin)))
    adaylar = [s for s in sonuclar if not s.get("icerik")
               and not any(d in s["url"] for d in _OKUNMAZ)][:adet]
    if not adaylar:
        return sum(1 for s in sonuclar if s.get("icerik"))
    isler = {_havuz.submit(_sayfa_paragraflari, s["url"], zaman_asimi - 0.5): s
             for s in adaylar}
    bitti, _ = wait(isler, timeout=zaman_asimi)
    for is_ in bitti:
        try:
            paragraflar = is_.result()
        except Exception:
            continue
        if paragraflar:
            isler[is_]["icerik"] = _ilgili_icerik(paragraflar, kokler)
    return sum(1 for s in sonuclar if s.get("icerik"))


# --- Modele ve kullaniciya sunma -----------------------------------------
def _tarih_metni(s):
    return s["tarih"].strftime("%d.%m.%Y") if s.get("tarih") else ""


def baglam_metni(sonuclar):
    """Arama sonuclarini [W1], [W2]... etiketli metne cevirir."""
    bugun = datetime.now().strftime("%d.%m.%Y")
    satirlar = [f"(Arama tarihi: {bugun}. Tarihi olan sonuçlar haberdir; "
                f"güncellik için tarihe bak.)"]
    for i, s in enumerate(sonuclar, 1):
        ust = " · ".join(p for p in (s.get("kaynak"), _tarih_metni(s),
                                      "haber" if s.get("tur") == "haber"
                                      else "web") if p)
        satirlar.append(f"[W{i}] {s['baslik']} ({ust})\nAdres: {s['url']}"
                        + (f"\n{s['ozet']}" if s.get("ozet") else "")
                        + (f"\nSayfa içeriğinden: {s['icerik']}"
                           if s.get("icerik") else ""))
    return "\n\n".join(satirlar)


def kaynakca(yanit, sonuclar):
    """
    Yanitin altina eklenen linkli kaynak listesi. Once modelin atif yaptigi
    kaynaklar; model hic atif yapmadiysa da bulunan sonuclar "ilgili
    linkler" olarak gosterilir (kullanici linkleri her zaman gorsun).
    """
    if not sonuclar:
        return ""
    atiflar = {int(n) for n in re.findall(r"\bW(\d{1,2})\b", yanit or "")}

    def satir(i, s):
        baslik = re.sub(r"[\[\]\n|]", " ", s["baslik"])[:100].strip()
        ek = " · ".join(p for p in (s.get("kaynak"), _tarih_metni(s)) if p)
        return f"- [W{i}] [{baslik}]({s['url']})" + (f" — {ek}" if ek else "")

    atifli = [satir(i, s) for i, s in enumerate(sonuclar, 1) if i in atiflar]
    diger = [satir(i, s) for i, s in enumerate(sonuclar, 1)
             if i not in atiflar]
    metin = "\n\n---\n**🌐 İnternet kaynakları**\n"
    if atifli:
        metin += "\n".join(atifli)
        if diger:
            metin += "\n\n*Diğer bulunan linkler:*\n" + "\n".join(diger)
    else:
        metin += "\n".join(diger)
    return metin
