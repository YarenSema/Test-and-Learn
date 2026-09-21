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

Supabase ayarlanmamissa (supabase_url / supabase_key yoksa) uygulama hicbir
sey degismemis gibi yerel dosyalarla calisir. Ayarli ama ulasilamiyorsa
kullanici uyarilir, islem yerel dosyaya yazilir ve BEKLEME_SURESI boyunca
bulut denenmez (her istekte zaman asimi beklenmesin diye). Bu sirada yerele
yazilan kayitlar bulut geri geldiginde otomatik senkronize EDILMEZ.

Kurulum: supabase_kurulum.sql dosyasini Supabase SQL Editor'de calistir,
sonra Streamlit secrets'a supabase_url ve supabase_key satirlarini ekle.
"""
import os
import json
import time
import uuid
import datetime

import streamlit as st
from dotenv import load_dotenv

load_dotenv()          # lokalde .env, Streamlit Cloud'da secrets kullanilir

# --- Yerel dosya yollari (bulut kapaliyken ve onbellek icin) --------------
CHATS_FILE = "chats.json"
FILES_DIR = "files"
FILES_META = os.path.join(FILES_DIR, "_files.json")
AKTIF_TESTLER_FILE = os.path.join(FILES_DIR, "_aktif_testler.json")
CACHE_DIR = os.path.join(FILES_DIR, "_bulut")   # buluttan inen dosyalar

# --- Supabase sabitleri ---------------------------------------------------
SOHBET_TABLO = "sohbetler"
DOSYA_TABLO = "dosyalar"
TEST_TABLO = "aktif_testler"
KOVA = "dosyalar"                  # storage bucket adi
ONBELLEK_SURESI = 15               # saniye: ayni veriyi tekrar tekrar cekme
ISTEK_ZAMAN_ASIMI = 8              # saniye: tek bir Supabase istegi
BEKLEME_SURESI = 60                # saniye: bulut hata verirse ne kadar susulur

# Bulut ulasilamaz oldugunda her istekte yeniden zaman asimi beklememek icin
# kisa bir "soguma" suresi tutulur; bu sure boyunca dogrudan yerele dusulur.
_bulut_bekleme_sonu = 0.0


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
    """Bulut az once hata verdi mi (kisa sure yerelden devam ediyoruz)?"""
    return time.time() < _bulut_bekleme_sonu


def bulut_acik():
    """Su an bulutla calisiliyor mu?"""
    return bulut_ayarli() and not bulut_beklemede()


def _bulut_hata(mesaj):
    """
    Bulut islemi basarisiz: kullaniciyi uyar ve kisa sure boyunca (soguma)
    dogrudan yerel kayda dus — her istekte zaman asimi beklenmesin.
    """
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
def _tablo_oku(tablo):
    """Tablodaki tum satirlari getirir."""
    yanit = supabase_client().table(tablo).select("*").execute()
    return yanit.data or []


def _tablo_yaz(tablo, kayit):
    """Kayit varsa gunceller, yoksa ekler (upsert — id birincil anahtar)."""
    supabase_client().table(tablo).upsert(kayit).execute()


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
    try:
        klasor = os.path.dirname(yol)
        if klasor:
            os.makedirs(klasor, exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _simdi():
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M")


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
    """Tum sohbetler (arsivdekiler dahil). Kisa sureli onbellekli."""
    if not bulut_acik():
        return _json_oku(CHATS_FILE)
    satirlar = _tablo_oku(SOHBET_TABLO)
    return dict(_sohbet_satirindan(s) for s in satirlar)


def sohbetleri_getir():
    """
    {cid: {title, messages, yazar, arsiv}} — hata olursa bos sozluk yerine
    elde ne varsa onu doner ki uygulama calismaya devam etsin.
    """
    try:
        sohbetler = _sohbetleri_oku()
    except Exception as e:
        _bulut_hata(f"Sohbetler okunamadı: {e}")
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


def sohbet_kaydet(cid, sohbet):
    """Tek bir sohbeti kaydeder (baskalarinin sohbetlerine dokunmadan)."""
    sohbet = dict(sohbet)
    sohbet.setdefault("arsiv", False)
    if bulut_acik():
        try:
            _tablo_yaz(SOHBET_TABLO, {
                "id": cid,
                "baslik": sohbet.get("title") or "Yeni sohbet",
                "yazar": sohbet.get("yazar") or "",
                "mesajlar": sohbet.get("messages") or [],
                "arsiv": bool(sohbet.get("arsiv")),
                "guncelleme": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(),
            })
            _sohbet_onbellegi_tazele()
            return True
        except Exception as e:
            _bulut_hata(f"Sohbet buluta kaydedilemedi: {e}")
    # Bulut yok ya da yazilamadi: yerel dosyaya yaz (veri kaybolmasin)
    hepsi = _json_oku(CHATS_FILE)
    hepsi[cid] = sohbet
    _json_yaz(CHATS_FILE, hepsi)
    _sohbet_onbellegi_tazele()
    return True


def sohbet_arsivle(cid, arsiv=True):
    sohbetler = sohbetleri_getir()
    if cid not in sohbetler:
        return False
    sohbet = sohbetler[cid]
    sohbet["arsiv"] = bool(arsiv)
    return sohbet_kaydet(cid, sohbet)


def sohbet_sil(cid):
    """Kalici silme (arsiv ekranindan)."""
    if bulut_acik():
        try:
            _tablo_sil(SOHBET_TABLO, cid)
            _sohbet_onbellegi_tazele()
            return True
        except Exception as e:
            _bulut_hata(f"Sohbet silinemedi: {e}")
            return False
    hepsi = _json_oku(CHATS_FILE)
    hepsi.pop(cid, None)
    _json_yaz(CHATS_FILE, hepsi)
    _sohbet_onbellegi_tazele()
    return True


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
    if not bulut_acik():
        yerel = _json_oku(FILES_META)
        for fid, bilgi in yerel.items():
            bilgi["id"] = fid
        return yerel
    satirlar = _tablo_oku(DOSYA_TABLO)
    return dict(_dosya_satirindan(s) for s in satirlar)


def _dosya_onbellegi_tazele():
    try:
        _dosyalari_oku.clear()
    except Exception:
        pass


def dosyalari_getir():
    try:
        return _dosyalari_oku()
    except Exception as e:
        _bulut_hata(f"Dosyalar okunamadı: {e}")
        yerel = _json_oku(FILES_META)
        for fid, bilgi in yerel.items():
            bilgi["id"] = fid
        return yerel


def dosya_kaydet(icerik, ad, kategori="Kampanya verisi", notu="",
                 yukleyen="", fid=None):
    """
    Yuklenen dosyayi saklar ve kaydini olusturur; id doner.
    `fid` verilirse o kimlikle yazilir (eski kayitlari aktarirken ayni
    dosyanin ikinci kez eklenmemesi icin).
    """
    fid = fid or uuid.uuid4().hex[:8]
    ad = os.path.basename(ad)
    boyut = len(icerik)

    if bulut_acik():
        yol = f"{fid}/{ad}"
        try:
            _depo_yukle(yol, icerik)
            _tablo_yaz(DOSYA_TABLO, {
                "id": fid, "ad": ad, "yol": yol, "kategori": kategori,
                "notu": notu, "hafizada": True, "yukleyen": yukleyen,
                "tarih": _simdi(), "boyut": boyut,
            })
            # Bu container icin yerel kopyayi da birakalim (tekrar inmesin)
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(os.path.join(CACHE_DIR, f"{fid}_{ad}"), "wb") as f:
                f.write(icerik)
            _dosya_onbellegi_tazele()
            return fid
        except Exception as e:
            _bulut_hata(f"Dosya buluta yüklenemedi: {e}")

    # Yerel kayit (bulut kapali ya da yazilamadi)
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
    _dosya_onbellegi_tazele()
    return fid


def dosya_guncelle(fid, **alanlar):
    """Dosya kaydinin alanlarini gunceller (orn. hafizada)."""
    bilgi = dosyalari_getir().get(fid)
    if not bilgi:
        return False
    bilgi = dict(bilgi)
    bilgi.update(alanlar)
    if bulut_acik():
        try:
            _tablo_yaz(DOSYA_TABLO, {
                "id": fid, "ad": bilgi.get("ad"), "yol": bilgi.get("yol"),
                "kategori": bilgi.get("kategori"), "notu": bilgi.get("not"),
                "hafizada": bool(bilgi.get("hafizada")),
                "yukleyen": bilgi.get("yukleyen"),
                "tarih": bilgi.get("tarih"), "boyut": bilgi.get("boyut"),
            })
            _dosya_onbellegi_tazele()
            return True
        except Exception as e:
            _bulut_hata(f"Dosya güncellenemedi: {e}")
            return False
    meta = _json_oku(FILES_META)
    if fid in meta:
        meta[fid].update(alanlar)
        _json_yaz(FILES_META, meta)
    _dosya_onbellegi_tazele()
    return True


def dosya_sil(fid):
    bilgi = dosyalari_getir().get(fid)
    if not bilgi:
        return False
    if bulut_acik():
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
@st.cache_data(ttl=ONBELLEK_SURESI, show_spinner=False)
def _testleri_oku():
    if not bulut_acik():
        return _json_oku(AKTIF_TESTLER_FILE)
    satirlar = _tablo_oku(TEST_TABLO)
    testler = {}
    for s in satirlar:
        bilgi = dict(s.get("veri") or {})
        bilgi["durum"] = s.get("durum") or bilgi.get("durum") or "aktif"
        testler[s["id"]] = bilgi
    return testler


def _test_onbellegi_tazele():
    try:
        _testleri_oku.clear()
    except Exception:
        pass


def testleri_getir():
    try:
        return _testleri_oku()
    except Exception as e:
        _bulut_hata(f"Aktif testler okunamadı: {e}")
        return _json_oku(AKTIF_TESTLER_FILE)


def test_kaydet(tid, bilgi):
    bilgi = dict(bilgi)
    bilgi.setdefault("durum", "aktif")
    if bulut_acik():
        try:
            _tablo_yaz(TEST_TABLO, {
                "id": tid, "veri": bilgi, "durum": bilgi["durum"],
                "guncelleme": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(),
            })
            _test_onbellegi_tazele()
            return True
        except Exception as e:
            _bulut_hata(f"Test buluta kaydedilemedi: {e}")
    hepsi = _json_oku(AKTIF_TESTLER_FILE)
    hepsi[tid] = bilgi
    _json_yaz(AKTIF_TESTLER_FILE, hepsi)
    _test_onbellegi_tazele()
    return True


def test_sil(tid):
    if bulut_acik():
        try:
            _tablo_sil(TEST_TABLO, tid)
            _test_onbellegi_tazele()
            return True
        except Exception as e:
            _bulut_hata(f"Test silinemedi: {e}")
            return False
    hepsi = _json_oku(AKTIF_TESTLER_FILE)
    hepsi.pop(tid, None)
    _json_yaz(AKTIF_TESTLER_FILE, hepsi)
    _test_onbellegi_tazele()
    return True


# =========================================================================
# DURUM BILGISI (kenar cubugunda gosterilir)
# =========================================================================
def durum_metni():
    if bulut_acik():
        return ("✅ Bulut depolama açık (Supabase) — sohbetler, dosyalar ve "
                "aktif testler kalıcı; herkes aynı veriyi görür.")
    if bulut_ayarli():      # ayarli ama az once hata verdi
        kalan = max(1, int(_bulut_bekleme_sonu - time.time()))
        return (f"⏳ Buluta şu anda ulaşılamıyor — {kalan} sn sonra yeniden "
                f"denenecek. Bu sırada kayıtlar geçici olarak bu sunucuda "
                f"tutuluyor.")
    return ("⚠️ Bulut depolama kapalı — veriler yalnızca bu sunucuda tutulur "
            "ve uygulama yeniden başlayınca silinir. (Kurulum için "
            "supabase_kurulum.sql)")
