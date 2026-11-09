"""
internet.py — sohbet icin hizli internet aramasi
------------------------------------------------
Gemini'nin kendi "Google Search" araci ucretsiz API anahtarinda kota hatasi
(429) verdigi icin arama uygulamanin kendisinde yapilir: `ddgs` paketi anahtar
istemez. Sonuclar modele kaynak olarak verilir.

Arama asla sohbeti bozamaz ya da yavaslatamaz: paket yoksa, sonuc cikmazsa
veya sure asilirsa bos liste doner ve asistan internet olmadan yanit verir.
"""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

ZAMAN_ASIMI = 4.0                  # saniye: bundan uzun arama beklenmez
SONUC_SAYISI = 5
OZET_UZUNLUGU = 500                # sonuc basina modele giden karakter

# Tek motor sik sik bos donuyor (olculen: yaklasik yarisi). Hepsine ayni anda
# sorulur, ilk dolu sonuc kullanilir; hem daha guvenilir hem daha hizli.
MOTORLAR = (("bing", "tr-tr"), ("google", "wt-wt"), ("yandex", "tr-tr"))

_havuz = ThreadPoolExecutor(max_workers=12, thread_name_prefix="arama")


def _ara(sorgu, adet, motor, bolge):
    from ddgs import DDGS
    return DDGS(timeout=int(ZAMAN_ASIMI)).text(
        sorgu, region=bolge, max_results=adet, backend=motor)


def ara(sorgu, adet=SONUC_SAYISI, zaman_asimi=ZAMAN_ASIMI):
    """[{baslik, url, ozet}] doner; herhangi bir sorunda bos liste."""
    sorgu = (sorgu or "").strip()
    if not sorgu:
        return []
    isler = [_havuz.submit(_ara, sorgu, adet, motor, bolge)
             for motor, bolge in MOTORLAR]
    try:
        for is_ in as_completed(isler, timeout=zaman_asimi):
            try:
                sonuclar = _temizle(is_.result())
            except Exception:
                continue                     # bu motor sonuc vermedi
            if sonuclar:
                return sonuclar
    except Exception:
        pass                                 # sure doldu
    return []


def _temizle(ham):
    sonuclar = []
    for r in ham or []:
        url = (r.get("href") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            continue
        sonuclar.append({
            "baslik": (r.get("title") or url).strip(),
            "url": url,
            "ozet": (r.get("body") or "").strip()[:OZET_UZUNLUGU],
        })
    return sonuclar


def baglam_metni(sonuclar):
    """Arama sonuclarini [W1], [W2]... etiketli metne cevirir."""
    return "\n\n".join(
        f"[W{i}] {s['baslik']}\nAdres: {s['url']}\n{s['ozet']}"
        for i, s in enumerate(sonuclar, 1))


def kaynakca(yanit, sonuclar):
    """Modelin yanitta gercekten atif yaptigi kaynaklarin listesi (yoksa '')."""
    # Model bazen [W1, W4] biciminde toplu atif yazar
    atiflar = {int(n) for n in re.findall(r"\bW(\d{1,2})\b", yanit or "")}
    satirlar = []
    for i, s in enumerate(sonuclar, 1):
        if i in atiflar:
            baslik = re.sub(r"[\[\]\n]", " ", s["baslik"])[:90].strip()
            satirlar.append(f"- [W{i}] [{baslik}]({s['url']})")
    if not satirlar:
        return ""
    return "\n\n---\n**🌐 İnternet kaynakları**\n" + "\n".join(satirlar)
