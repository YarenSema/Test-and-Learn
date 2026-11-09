"""
depo.py — kalici depolama katmani (sohbetler, dosyalar, aktif testler)
---------------------------------------------------------------------
Streamlit Cloud'un diski gecicidir: uygulama uyuyup uyandiginda ya da yeni
bir surum yayinlandiginda yerel dosyalar (chats.json, files/) silinir.
Bu modul, ayarlanmissa her seyi Supabase'te saklar; boylece:
  - sohbetler ve yuklenen dosyalar silinmez,
  - ayni linke giren herkes (farkli cihazlardan da) ayni veriyi gorur.

Baglanti tek yerden kurulur: supabase_client() (resmi supabase-py istemcisi,
@st.cache_resource ile onbellekli). Anahtarlar once st.secrets'tan, yoksa
.env / ortam degiskeninden okunur.

TEK DOGRU KAYNAK KURALI
  Supabase ayarlanmamissa uygulama yerel dosyalarla calisir. Ayarliysa TEK
  dogru kaynak buluttur; yerel chats.json / _aktif_testler.json / _files.json
  bir daha okunmaz ve bulutla karismaz. Bulut gecici olarak ulasilamazsa:
    - okumalarda son basarili bulut goruntusu gosterilir,
    - sohbet ve test kayitlari siraya alinir (_bekleyen_kayitlar.json) ve
      bulut geri geldiginde otomatik gonderilir,
    - dosya yukleme ve silme hata mesajiyla reddedilir.

AYNI ANDA YAZMA
  Tablo guncellemeleri kaydin tamamini degil, yalnizca degisen alani yazar.
  Sohbet kaydedilirken buluttaki mesajlar okunup birlestirilir; ayni sohbete
  iki kisi yazsa da birinin mesaji silinmez.

Kurulum: supabase_kurulum.sql dosyasini Supabase SQL Editor'de calistir,
sonra Streamlit secrets'a supabase_url ve supabase_key satirlarini ekle.
"""
import copy
import os
import json
import sys
import threading
import time
import uuid
import datetime

import streamlit as st
from dotenv import load_dotenv

load_dotenv()          # lokalde .env, Streamlit Cloud'da secrets kullanilir

# Sirket aginda HTTPS trafigi kurumsal sertifikayla imzalanir; Python'un kendi
# sertifika listesi bunu tanimaz ve Supabase baglantisi SSL hatasi verir.
# Windows'un sertifika deposunu kullaniyoruz (dogrulama kapanmaz).
if sys.platform == "win32":
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:
        pass

# --- Yerel dosya yollari (bulut kapaliyken ve onbellek icin) --------------
CHATS_FILE = "chats.json"
FILES_DIR = "files"
FILES_META = os.path.join(FILES_DIR, "_files.json")
AKTIF_TESTLER_FILE = os.path.join(FILES_DIR, "_aktif_testler.json")
CACHE_DIR = os.path.join(FILES_DIR, "_bulut")   # buluttan inen dosyalar
BEKLEYEN_FILE = os.path.join(FILES_DIR, "_bekleyen_kayitlar.json")

# --- Supabase sabitleri ---------------------------------------------------
SOHBET_TABLO = "sohbetler"
DOSYA_TABLO = "dosyalar"
TEST_TABLO = "aktif_testler"
KOVA = "dosyalar"                  # storage bucket adi
ONBELLEK_SURESI = 15               # saniye: ayni veriyi tekrar tekrar cekme
ISTEK_ZAMAN_ASIMI = 8              # saniye: tek bir Supabase istegi
BEKLEME_SURESI = 20                # saniye: bulut hata verirse ne kadar susulur

# Bulut ulasilamaz oldugunda her istekte yeniden zaman asimi beklememek icin
# kisa bir "soguma" suresi tutulur.
_bulut_bekleme_sonu = 0.0
_son_goruntu = {}                  # tur -> son basarili bulut okumasi
_bekleyen_kilidi = threading.Lock()


def _ayar(*adlar):
    """Secrets ya da ortam degiskeninden ilk dolu degeri getirir."""
    for ad in adlar:
        try:
            deger = st.secrets[ad]
        except Exception:
            deger = None
        if deger:
            return str(deger).strip()
    for ad in adlar:
        deger = os.getenv(ad.upper())
        if deger:
            return deger.strip()
    return None


@st.cache_resource(show_spinner=False)
def supabase_client():
    """
    Supabase istemcisi — uygulamada tek yerden kurulur ve onbellege alinir.
    Anahtarlar once st.secrets'tan (Streamlit Cloud), yoksa .env / ortam
    degiskeninden (lokal) okunur. Ayar yoksa ya da istemci kurulamazsa None
    doner; bu durumda uygulama yerel dosyalarla calismaya devam eder.
    """
    url = _ayar("supabase_url", "SUPABASE_URL")
    key = _ayar("supabase_key", "SUPABASE_KEY", "supabase_anon_key")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        from supabase.client import ClientOptions
        return create_client(
            url.rstrip("/"), key,
            options=ClientOptions(
                postgrest_client_timeout=ISTEK_ZAMAN_ASIMI,
                storage_client_timeout=60,      # dosya yukleme daha uzun surer
            ))
    except Exception as e:
        hata_bildir(f"Supabase istemcisi kurulamadı: {e}")
        return None


def bulut_ayarli():
    """Supabase anahtarlari tanimli mi (erisilebilir olmasi ayri konu)?"""
    return supabase_client() is not None


def bulut_beklemede():
    """Bulut az once hata verdi mi (kisa sure tekrar denenmiyor mu)?"""
    return time.time() < _bulut_bekleme_sonu


def bulut_acik():
    """Su an bulutla calisiliyor mu?"""
    return bulut_ayarli() and not bulut_beklemede()


def _bulut_hata(mesaj):
    """Bulut islemi basarisiz: kullaniciyi uyar, kisa sure tekrar deneme."""
    global _bulut_bekleme_sonu
    _bulut_bekleme_sonu = time.time() + BEKLEME_SURESI
    hata_bildir(mesaj)


def hata_bildir(mesaj):
    """Son bulut hatasini saklar (kenar cubugunda gosterilir)."""
    try:
        st.session_state["_depo_hata"] = str(mesaj)[:300]
    except Exception:
        # Streamlit disinda (orn. aktar_supabase.py) calisiyoruz
        print(f"[depo] {mesaj}")


def son_hata():
    try:
        return st.session_state.get("_depo_hata")
    except Exception:
        return None


def hatayi_temizle():
    try:
        st.session_state.pop("_depo_hata", None)
    except Exception:
        pass


# --- Supabase islemleri (tablolar + dosya deposu) ------------------------
def _tablo_oku(tablo, sira=None):
    """Tablodaki tum satirlari getirir (Postgres sira garantisi vermez)."""
    sorgu = supabase_client().table(tablo).select("*")
    if sira:
        sorgu = sorgu.order(sira)
    return sorgu.execute().data or []


def _tablo_satiri(tablo, kimlik, alanlar="*"):
    """Tek satiri onbellege bakmadan okur (yoksa None)."""
    yanit = (supabase_client().table(tablo).select(alanlar)
             .eq("id", kimlik).limit(1).execute())
    return yanit.data[0] if yanit.data else None


def _tablo_yaz(tablo, kayit):
    """Kayit varsa gunceller, yoksa ekler (upsert — id birincil anahtar)."""
    supabase_client().table(tablo).upsert(kayit).execute()


def _tablo_guncelle(tablo, kimlik, alanlar):
    """Yalnizca verilen alanlari yazar; baskasinin degisikligini ezmez."""
    supabase_client().table(tablo).update(alanlar).eq("id", kimlik).execute()


def _tablo_sil(tablo, kimlik):
    supabase_client().table(tablo).delete().eq("id", kimlik).execute()


def _depo_yukle(yol, icerik):
    """Dosyayi 'dosyalar' kovasina yukler (ayni yol varsa uzerine yazar)."""
    supabase_client().storage.from_(KOVA).upload(
        path=yol, file=icerik,
        file_options={"content-type": "application/octet-stream",
                      "upsert": "true"})


def _depo_indir(yol):
    return supabase_client().storage.from_(KOVA).download(yol)


def _depo_sil(yol):
    supabase_client().storage.from_(KOVA).remove([yol])


# --- Yerel JSON yardimcilari ---------------------------------------------
def _json_oku(yol, varsayilan=None):
    try:
        with open(yol, "r", encoding="utf-8") as f:
            veri = json.load(f)
        return veri if isinstance(veri, dict) else (varsayilan or {})
    except Exception:
        return varsayilan if varsayilan is not None else {}


def _json_yaz(yol, veri):
    """Once gecici dosyaya yazar; yarim kalan yazma kaydi bozmaz."""
    try:
        klasor = os.path.dirname(yol)
        if klasor:
            os.makedirs(klasor, exist_ok=True)
        gecici = f"{yol}.{uuid.uuid4().hex[:6]}.tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
        os.replace(gecici, yol)
        return True
    except Exception:
        return False


def _simdi():
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M")


def _simdi_utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# --- Buluttan guvenli okuma ----------------------------------------------
def _buluttan_oku(tur, okuyucu, hata_metni):
    """
    Bulutu okur; ulasilamazsa son basarili goruntuyu doner. Yerel dosyalara
    asla dusmez — eski yerel kopya ortak listeyle karismasin diye.
    """
    if not bulut_beklemede():
        try:
            veri = okuyucu()
            _son_goruntu[tur] = copy.deepcopy(veri)
            return veri
        except Exception as e:
            _bulut_hata(f"{hata_metni}: {e}")
    return copy.deepcopy(_son_goruntu.get(tur, {}))


# --- Bekleyen kayitlar: bulut yokken yazilanlar kaybolmasin ---------------
def _siraya_al(tablo, kayit, birlestir=False):
    """Yazilamayan kaydi siraya alir; ayni kaydin son hali gecerlidir."""
    with _bekleyen_kilidi:
        hepsi = _json_oku(BEKLEYEN_FILE)
        hepsi[f"{tablo}:{kayit['id']}"] = {
            "tablo": tablo, "kayit": kayit, "birlestir": birlestir}
        return _json_yaz(BEKLEYEN_FILE, hepsi)


def bekleyen_sayisi():
    return len(_json_oku(BEKLEYEN_FILE))


def _bekleyen_kayitlar(tablo):
    return [b["kayit"] for b in _json_oku(BEKLEYEN_FILE).values()
            if b.get("tablo") == tablo]


def _kayit_gonder(tablo, kayit, birlestir=False):
    if tablo == SOHBET_TABLO and birlestir:
        kayit = _bulutla_birlestir(kayit)
    _tablo_yaz(tablo, kayit)


def bekleyenleri_gonder():
    """Bulut geri geldiyse siradaki kayitlari sirayla gonderir."""
    if not bulut_acik() or not os.path.exists(BEKLEYEN_FILE):
        return
    with _bekleyen_kilidi:
        hepsi = _json_oku(BEKLEYEN_FILE)
        try:
            for anahtar in list(hepsi):
                b = hepsi[anahtar]
                _kayit_gonder(b["tablo"], b["kayit"],
                              bool(b.get("birlestir")))
                del hepsi[anahtar]
        except Exception as e:
            _bulut_hata(f"Bekleyen kayıtlar gönderilemedi: {e}")
        if hepsi:
            _json_yaz(BEKLEYEN_FILE, hepsi)
        else:
            try:
                os.remove(BEKLEYEN_FILE)
            except OSError:
                pass
    _sohbet_onbellegi_tazele()
    _test_onbellegi_tazele()


def _bulut_saglikli_ise_uyariyi_temizle():
    """Bulut duzeldiyse eski uyari ekranda takili kalmasin."""
    if son_hata() and bulut_acik() and not bekleyen_sayisi():
        hatayi_temizle()


# =========================================================================
# SOHBETLER
# =========================================================================
def _sohbet_satirindan(satir):
    return satir["id"], {
        "title": satir.get("baslik") or "Yeni sohbet",
        "messages": satir.get("mesajlar") or [],
        "yazar": satir.get("yazar") or "",
        "arsiv": bool(satir.get("arsiv")),
        "guncelleme": satir.get("guncelleme") or "",
    }


@st.cache_data(ttl=ONBELLEK_SURESI, show_spinner=False)
def _sohbetleri_oku():
    """Bulut: tum sohbetler (arsivdekiler dahil), eskiden yeniye."""
    satirlar = _tablo_oku(SOHBET_TABLO, sira="guncelleme")
    return dict(_sohbet_satirindan(s) for s in satirlar)


def sohbetleri_getir():
    """{cid: {title, messages, yazar, arsiv}} — ekranda gosterilecek liste."""
    if bulut_ayarli():
        bekleyenleri_gonder()
        sohbetler = _buluttan_oku("sohbet", _sohbetleri_oku,
                                  "Sohbetler okunamadı")
        for satir in _bekleyen_kayitlar(SOHBET_TABLO):
            cid, sohbet = _sohbet_satirindan(satir)
            sohbetler[cid] = sohbet
        _bulut_saglikli_ise_uyariyi_temizle()
    else:
        sohbetler = _json_oku(CHATS_FILE)
    # Eski kayitlarda olmayan alanlari tamamla
    for s in sohbetler.values():
        s.setdefault("messages", [])
        s.setdefault("title", "Yeni sohbet")
        s.setdefault("yazar", "")
        s.setdefault("arsiv", False)
    return sohbetler


def _sohbet_onbellegi_tazele():
    try:
        _sohbetleri_oku.clear()
    except Exception:
        pass


def _mesajlari_birlestir(buluttaki, bizdeki):
    """
    Ortak baslangictan sonra ikisine de eklenen mesajlari korur. Ayni sohbete
    iki kisi yazdiginda sonra kaydedenin digerini silmesini engeller.
    """
    ortak = 0
    for a, b in zip(buluttaki, bizdeki):
        if a != b:
            break
        ortak += 1
    return list(buluttaki) + list(bizdeki[ortak:])


def _bulutla_birlestir(kayit):
    satir = _tablo_satiri(SOHBET_TABLO, kayit["id"], "mesajlar")
    if not satir:
        return kayit
    kayit = dict(kayit)
    kayit["mesajlar"] = _mesajlari_birlestir(satir.get("mesajlar") or [],
                                             kayit.get("mesajlar") or [])
    return kayit


def sohbet_kaydet(cid, sohbet, birlestir=True):
    """
    Tek bir sohbeti kaydeder (baskalarinin sohbetlerine dokunmadan).
    `birlestir=False`: mesaj bilerek silindiyse (soruyu geri al) kullanilir;
    aksi halde silinen mesaj buluttan geri gelirdi.
    """
    sohbet = dict(sohbet)
    sohbet.setdefault("arsiv", False)
    if not bulut_ayarli():
        hepsi = _json_oku(CHATS_FILE)
        hepsi[cid] = sohbet
        _json_yaz(CHATS_FILE, hepsi)
        return True

    kayit = {
        "id": cid,
        "baslik": sohbet.get("title") or "Yeni sohbet",
        "yazar": sohbet.get("yazar") or "",
        "mesajlar": sohbet.get("messages") or [],
        "arsiv": bool(sohbet.get("arsiv")),
        "guncelleme": _simdi_utc(),
    }
    if bulut_acik():
        try:
            _kayit_gonder(SOHBET_TABLO, kayit, birlestir)
            _sohbet_onbellegi_tazele()
            return True
        except Exception as e:
            _bulut_hata(f"Sohbet buluta kaydedilemedi: {e}")
    return _siraya_al(SOHBET_TABLO, kayit, birlestir)


def sohbet_arsivle(cid, arsiv=True):
    """Yalnizca arsiv alanini yazar; sohbetin mesajlarina dokunmaz."""
    if not bulut_ayarli():
        hepsi = _json_oku(CHATS_FILE)
        if cid not in hepsi:
            return False
        hepsi[cid]["arsiv"] = bool(arsiv)
        _json_yaz(CHATS_FILE, hepsi)
        return True
    try:
        _tablo_guncelle(SOHBET_TABLO, cid, {"arsiv": bool(arsiv)})
        _sohbet_onbellegi_tazele()
        return True
    except Exception as e:
        _bulut_hata(f"Sohbet arşivlenemedi: {e}")
        return False


def sohbet_sil(cid):
    """Kalici silme (arsiv ekranindan)."""
    if not bulut_ayarli():
        hepsi = _json_oku(CHATS_FILE)
        hepsi.pop(cid, None)
        _json_yaz(CHATS_FILE, hepsi)
        return True
    try:
        _tablo_sil(SOHBET_TABLO, cid)
        _sohbet_onbellegi_tazele()
        return True
    except Exception as e:
        _bulut_hata(f"Sohbet silinemedi: {e}")
        return False


# =========================================================================
# DOSYALAR
# =========================================================================
def _dosya_satirindan(satir):
    return satir["id"], {
        "id": satir["id"],
        "ad": satir.get("ad") or "dosya",
        "yol": satir.get("yol") or "",
        "kategori": satir.get("kategori") or "-",
        "not": satir.get("notu") or "",
        "hafizada": bool(satir.get("hafizada", True)),
        "yukleyen": satir.get("yukleyen") or "",
        "tarih": satir.get("tarih") or "",
        "boyut": satir.get("boyut") or 0,
    }


@st.cache_data(ttl=ONBELLEK_SURESI, show_spinner=False)
def _dosyalari_oku():
    satirlar = _tablo_oku(DOSYA_TABLO)
    return dict(_dosya_satirindan(s) for s in satirlar)


def _dosya_onbellegi_tazele():
    try:
        _dosyalari_oku.clear()
    except Exception:
        pass


def dosyalari_getir():
    if bulut_ayarli():
        return _buluttan_oku("dosya", _dosyalari_oku, "Dosyalar okunamadı")
    yerel = _json_oku(FILES_META)
    for fid, bilgi in yerel.items():
        bilgi["id"] = fid
    return yerel


def dosya_kaydet(icerik, ad, kategori="Kampanya verisi", notu="",
                 yukleyen="", fid=None):
    """
    Yuklenen dosyayi saklar ve kaydini olusturur; id doner.
    `fid` verilirse o kimlikle yazilir (eski kayitlari aktarirken ayni
    dosyanin ikinci kez eklenmemesi icin). Bulut ayarli ama yukleme
    basarisizsa None doner: dosya kimsenin goremeyecegi bir yere yazilmaz.
    """
    fid = fid or uuid.uuid4().hex[:8]
    ad = os.path.basename(ad)
    boyut = len(icerik)

    if bulut_ayarli():
        yol = f"{fid}/{ad}"
        try:
            _depo_yukle(yol, icerik)
            _tablo_yaz(DOSYA_TABLO, {
                "id": fid, "ad": ad, "yol": yol, "kategori": kategori,
                "notu": notu, "hafizada": True, "yukleyen": yukleyen,
                "tarih": _simdi(), "boyut": boyut,
            })
        except Exception as e:
            _bulut_hata(f"Dosya buluta yüklenemedi ({ad}): {e}")
            return None
        # Bu container icin yerel kopyayi da birakalim (tekrar inmesin)
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(os.path.join(CACHE_DIR, f"{fid}_{ad}"), "wb") as f:
                f.write(icerik)
        except OSError:
            pass
        _dosya_onbellegi_tazele()
        return fid

    # Yerel kayit (bulut ayarli degil)
    os.makedirs(FILES_DIR, exist_ok=True)
    disk_adi = f"{fid}_{ad}"
    with open(os.path.join(FILES_DIR, disk_adi), "wb") as f:
        f.write(icerik)
    meta = _json_oku(FILES_META)
    meta[fid] = {
        "ad": ad, "disk_adi": disk_adi, "kategori": kategori, "not": notu,
        "hafizada": True, "yukleyen": yukleyen, "tarih": _simdi(),
        "boyut": boyut,
    }
    _json_yaz(FILES_META, meta)
    return fid


def dosya_guncelle(fid, **alanlar):
    """Dosya kaydinin yalnizca verilen alanlarini gunceller (orn. hafizada)."""
    if bulut_ayarli():
        # Ekrandaki "not" alani tabloda "notu" kolonudur
        kolonlar = {("notu" if k == "not" else k): v
                    for k, v in alanlar.items()}
        try:
            _tablo_guncelle(DOSYA_TABLO, fid, kolonlar)
            _dosya_onbellegi_tazele()
            return True
        except Exception as e:
            _bulut_hata(f"Dosya güncellenemedi: {e}")
            return False
    meta = _json_oku(FILES_META)
    if fid not in meta:
        return False
    meta[fid].update(alanlar)
    _json_yaz(FILES_META, meta)
    return True


def dosya_sil(fid):
    bilgi = dosyalari_getir().get(fid)
    if not bilgi:
        return False
    if bulut_ayarli():
        try:
            if bilgi.get("yol"):
                try:
                    _depo_sil(bilgi["yol"])
                except Exception:
                    pass          # depoda yoksa kaydi yine de silelim
            _tablo_sil(DOSYA_TABLO, fid)
        except Exception as e:
            _bulut_hata(f"Dosya silinemedi: {e}")
            return False
    else:
        meta = _json_oku(FILES_META)
        eski = meta.pop(fid, None)
        if eski:
            try:
                os.remove(os.path.join(FILES_DIR, eski["disk_adi"]))
            except Exception:
                pass
            _json_yaz(FILES_META, meta)
    # Yerel onbellek kopyasi
    try:
        onbellek = os.path.join(CACHE_DIR, f"{fid}_{bilgi.get('ad', '')}")
        if os.path.exists(onbellek):
            os.remove(onbellek)
    except Exception:
        pass
    _dosya_onbellegi_tazele()
    return True


def dosya_yolu(bilgi):
    """
    Dosyanin okunabilecegi yerel yolu doner. Bulut modunda dosya ilk
    istendiginde indirilip onbellege alinir; sonraki okumalar diskten olur.
    """
    if not bilgi:
        return ""
    if bilgi.get("disk_adi"):                       # yerel kayit
        return os.path.join(FILES_DIR, bilgi["disk_adi"])

    fid, ad = bilgi.get("id", ""), bilgi.get("ad", "dosya")
    yerel = os.path.join(CACHE_DIR, f"{fid}_{ad}")
    if os.path.exists(yerel):
        return yerel
    if not bulut_acik() or not bilgi.get("yol"):
        return yerel                                # yok; cagiran taraf anlar
    try:
        icerik = _depo_indir(bilgi["yol"])
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(yerel, "wb") as f:
            f.write(icerik)
    except Exception as e:
        _bulut_hata(f"Dosya indirilemedi ({ad}): {e}")
    return yerel


def dosya_icerigi(bilgi):
    """Indirme butonu icin ham icerik (bulunamazsa None)."""
    yol = dosya_yolu(bilgi)
    try:
        with open(yol, "rb") as f:
            return f.read()
    except Exception:
        return None


# =========================================================================
# AKTIF TESTLER
# =========================================================================
def _test_satirindan(satir):
    bilgi = dict(satir.get("veri") or {})
    # Kolon ve JSON ayrismasin: gecerli durum her zaman kolondaki degerdir
    bilgi["durum"] = satir.get("durum") or bilgi.get("durum") or "aktif"
    return satir["id"], bilgi


@st.cache_data(ttl=ONBELLEK_SURESI, show_spinner=False)
def _testleri_oku():
    """Bulut: tum testler, eskiden yeniye."""
    satirlar = _tablo_oku(TEST_TABLO, sira="guncelleme")
    return dict(_test_satirindan(s) for s in satirlar)


def _test_onbellegi_tazele():
    try:
        _testleri_oku.clear()
    except Exception:
        pass


def testleri_getir():
    if not bulut_ayarli():
        return _json_oku(AKTIF_TESTLER_FILE)
    testler = _buluttan_oku("test", _testleri_oku, "Aktif testler okunamadı")
    for satir in _bekleyen_kayitlar(TEST_TABLO):
        tid, bilgi = _test_satirindan(satir)
        testler[tid] = bilgi
    return testler


def test_kaydet(tid, bilgi):
    bilgi = dict(bilgi)
    bilgi.setdefault("durum", "aktif")
    if not bulut_ayarli():
        hepsi = _json_oku(AKTIF_TESTLER_FILE)
        hepsi[tid] = bilgi
        _json_yaz(AKTIF_TESTLER_FILE, hepsi)
        return True

    kayit = {"id": tid, "veri": bilgi, "durum": bilgi["durum"],
             "guncelleme": _simdi_utc()}
    if bulut_acik():
        try:
            _kayit_gonder(TEST_TABLO, kayit)
            _test_onbellegi_tazele()
            return True
        except Exception as e:
            _bulut_hata(f"Test buluta kaydedilemedi: {e}")
    return _siraya_al(TEST_TABLO, kayit)


def test_guncelle(tid, **alanlar):
    """
    Testin verilen alanlarini gunceller. Bulut acikken guncel kayit
    onbellege bakilmadan okunur: baskasinin az once yaptigi degisiklik ezilmez.
    """
    if bulut_acik():
        try:
            satir = _tablo_satiri(TEST_TABLO, tid)
            if not satir:
                _test_onbellegi_tazele()
                return False
            bilgi = _test_satirindan(satir)[1]
        except Exception as e:
            _bulut_hata(f"Test okunamadı: {e}")
            bilgi = testleri_getir().get(tid)
    else:
        bilgi = testleri_getir().get(tid)
    if not bilgi:
        return False
    bilgi = dict(bilgi)
    bilgi.update(alanlar)
    return test_kaydet(tid, bilgi)


def test_sil(tid):
    if not bulut_ayarli():
        hepsi = _json_oku(AKTIF_TESTLER_FILE)
        hepsi.pop(tid, None)
        _json_yaz(AKTIF_TESTLER_FILE, hepsi)
        return True
    try:
        _tablo_sil(TEST_TABLO, tid)
        _test_onbellegi_tazele()
        return True
    except Exception as e:
        _bulut_hata(f"Test silinemedi: {e}")
        return False


# =========================================================================
# DURUM BILGISI (kenar cubugunda gosterilir)
# =========================================================================
def durum_metni():
    bekleyen = bekleyen_sayisi() if bulut_ayarli() else 0
    if bulut_acik() and not bekleyen:
        return ("✅ Bulut depolama açık (Supabase) — sohbetler, dosyalar ve "
                "aktif testler kalıcı; herkes aynı veriyi görür.")
    if bulut_ayarli():
        ek = (f" {bekleyen} kayıt sırada, bulut geri gelince otomatik "
              f"gönderilecek." if bekleyen else "")
        return ("⏳ Buluta şu anda ulaşılamıyor; son bilinen veriler "
                "gösteriliyor, otomatik yeniden denenecek." + ek)
    return ("⚠️ Bulut depolama kapalı — veriler yalnızca bu sunucuda tutulur "
            "ve uygulama yeniden başlayınca silinir. (Kurulum için "
            "supabase_kurulum.sql)")
