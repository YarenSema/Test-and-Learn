"""
app.py  (Digital Marketing Test & Learn - v4)
----------------------------------------------
v3'e ek olarak: sol panelde "Dosyalarim" bolumu — gercek Test & Learn ve
kampanya verilerini yukleyip kalici olarak saklama, baskalarinin acip
inceleyebilmesi ve istenirse asistanin hafizasina (bilgi tabanina) ekleme.
Yuklenen dosyalar files/ klasorunde, bilgileri files/_files.json icinde durur.
Calistir:  python -m streamlit run app.py
"""
import streamlit as st

# Login kontrolü
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.set_page_config(page_title="Login")
    st.markdown("# 🔐 Digital Marketing Test & Learn")
    
    password = st.text_input("Şifre gir:", type="password", key="login_pass")
    
    if password == "digital123":  # BURAYA KENDİ ŞİFREN YAZ
        st.session_state.authenticated = True
        st.rerun()
    elif password:
        st.error("❌ Yanlış şifre!")
    st.stop()



import os
import json
import time
import uuid
import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai import types
from metrics import compute_metrics, metrics_to_text
import test_havuzu as th

load_dotenv()
# Gemini API key'i Streamlit secrets'ten al (production) veya .env'den (lokal)
api_key = st.secrets.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

st.set_page_config(page_title="Digital Marketing Test & Learn",
                   page_icon="🧪", layout="wide")

CHATS_FILE = "chats.json"          # sohbetlerin kaydedildigi yerel dosya
FILES_DIR = "files"                # yuklenen dosyalarin durdugu klasor
FILES_META = os.path.join(FILES_DIR, "_files.json")   # dosya bilgileri
TABLE_EXT = (".csv", ".xlsx", ".xls")

# Sirayla denenecek modeller: ilki mesgulse otomatik digerine gecilir.
MODELLER = ["gemini-flash-latest", "gemini-2.5-flash",
            "gemini-2.0-flash", "gemini-flash-lite-latest"]
DENEME_SAYISI = 3                  # ayni model icin tekrar deneme adedi


# --- Sohbet kaydetme/yukleme (kalicilik) ----------------------------------
def load_chats():
    try:
        with open(CHATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_chats(chats):
    try:
        with open(CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(chats, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # kaydedilemezse uygulama yine calisir


def new_chat():
    cid = uuid.uuid4().hex[:8]
    st.session_state.chats[cid] = {"title": "Yeni sohbet", "messages": []}
    st.session_state.active = cid
    st.session_state.view = "chat"
    save_chats(st.session_state.chats)


# --- Dosyalarim: kayit / okuma / silme ------------------------------------
def load_files_meta():
    """Yuklenen dosyalarin listesini (id -> bilgi) getirir."""
    try:
        with open(FILES_META, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_files_meta(meta):
    try:
        os.makedirs(FILES_DIR, exist_ok=True)
        with open(FILES_META, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def save_uploaded_file(uploaded, kategori="Kampanya verisi", not_metni=""):
    """Yuklenen dosyayi diske yazar ve kaydini olusturur. id doner."""
    os.makedirs(FILES_DIR, exist_ok=True)
    fid = uuid.uuid4().hex[:8]
    orijinal = os.path.basename(uploaded.name)
    disk_adi = f"{fid}_{orijinal}"
    with open(os.path.join(FILES_DIR, disk_adi), "wb") as f:
        f.write(uploaded.getbuffer())

    meta = load_files_meta()
    meta[fid] = {
        "ad": orijinal,
        "disk_adi": disk_adi,
        "kategori": kategori,
        "not": not_metni,
        "hafizada": True,   # varsayilan: asistan bu dosyayi da okusun
        "tarih": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        "boyut": os.path.getsize(os.path.join(FILES_DIR, disk_adi)),
    }
    save_files_meta(meta)
    return fid


def delete_file(fid):
    meta = load_files_meta()
    bilgi = meta.pop(fid, None)
    if bilgi:
        try:
            os.remove(os.path.join(FILES_DIR, bilgi["disk_adi"]))
        except Exception:
            pass
        save_files_meta(meta)


def file_path(bilgi):
    return os.path.join(FILES_DIR, bilgi["disk_adi"])


@st.cache_data(show_spinner=False)
def read_tables(path, mtime):
    """
    CSV/Excel dosyasini {sayfa adi: tablo} sozluguna cevirir.
    Excel cok sayfali olabilir (orn. banyo kategorisi dosyasi), o yuzden
    tek tablo degil tum sayfalar okunur. mtime sadece cache anahtaridir.
    """
    alt = path.lower()
    if alt.endswith(".csv"):
        for kodlama in ("utf-8", "utf-8-sig", "cp1254", "latin-1"):
            try:
                return {"veri": pd.read_csv(path, encoding=kodlama, sep=None,
                                            engine="python")}
            except UnicodeDecodeError:
                continue
            except Exception:
                # ayrac tahmini tutmazsa duz virgulle dene
                try:
                    return {"veri": pd.read_csv(path, encoding=kodlama)}
                except Exception:
                    continue
        return {}
    if alt.endswith((".xlsx", ".xls")):
        try:
            sayfalar = pd.read_excel(path, sheet_name=None)
            return {str(ad): df for ad, df in sayfalar.items()}
        except Exception:
            return {}
    return {}


def load_tables(bilgi):
    """Kayitli dosyanin tum sayfalarini okur ({} = okunamadi)."""
    yol = file_path(bilgi)
    if not os.path.exists(yol):
        return {}
    if not yol.lower().endswith(TABLE_EXT):
        return {}
    try:
        return read_tables(yol, os.path.getmtime(yol))
    except Exception:
        return {}


def load_table(bilgi):
    """Kayitli dosyanin ilk sayfasini tablo olarak okur (okunamazsa None)."""
    sayfalar = load_tables(bilgi)
    if not sayfalar:
        return None
    return next(iter(sayfalar.values()))


# --- Yuklenen dosyayi asistanin okuyabilecegi metne cevirme ---------------
KB_KOLONLARI = ["deney_id", "donem", "urun", "amac", "platform",
                "hedef_kitle", "test_edilen_degisken", "kazanan",
                "etki", "ogrenim"]


def kb_satirlarina_cevir(df):
    """Bilgi tabani formatindaki tabloyu ogrenim satirlarina cevirir."""
    satirlar = []
    for _, r in df.iterrows():
        satirlar.append(
            f"[{r['deney_id']} | {r['donem']} | {r['urun']} | {r['amac']} | "
            f"{r['platform']} | {r['hedef_kitle']}] "
            f"Test: {r['test_edilen_degisken']} → Kazanan: {r['kazanan']} "
            f"({r['etki']}). Öğrenim: {r['ogrenim']}"
        )
    return satirlar


def tablo_metne_cevir(df, max_satir=80):
    """
    Tek bir tabloyu asistanin okuyacagi metne cevirir. Format tanima:
    - Bilgi tabani formati (deney_id, donem, ...)  -> ogrenim satirlari
    - Banyo kategorisi deney formati (Test_ID, ...) -> deney satirlari
    - Diger tablolar                               -> metrikler + ilk satirlar
    """
    if df is None or df.empty:
        return None

    kolonlar = [str(c).strip().lower() for c in df.columns]
    if all(k in kolonlar for k in KB_KOLONLARI):
        df2 = df.copy()
        df2.columns = kolonlar
        return "\n".join(kb_satirlarina_cevir(df2))

    if th.is_test_table(df):
        return "\n\n".join(th.test_satirlari(df.head(max_satir)))

    parcalar = [f"Satır sayısı: {len(df)} | Kolonlar: "
                f"{', '.join(str(c) for c in df.columns)}"]
    try:
        metrikler = compute_metrics(df)
        if any(v for v in metrikler.values()):
            parcalar.append("Hesaplanan metrikler (koddan gelir, DOĞRUdur):")
            parcalar.append(metrics_to_text(metrikler))
    except Exception:
        pass
    parcalar.append(f"Veriden örnek (ilk {min(max_satir, len(df))} satır):")
    parcalar.append(df.head(max_satir).to_csv(index=False))
    return "\n".join(parcalar)


def dosya_metne_cevir(bilgi, max_satir=80, max_sayfa=8):
    """Yuklenen bir dosyanin tum sayfalarini asistana verilecek metne cevirir."""
    sayfalar = load_tables(bilgi)
    if not sayfalar:
        return None

    baslik = (f"### DOSYA: {bilgi['ad']} "
              f"({bilgi.get('kategori', '-')}, yüklenme: {bilgi.get('tarih', '-')})")
    if bilgi.get("not"):
        baslik += f"\nNot: {bilgi['not']}"

    bloklar = [baslik]
    tek_sayfa = len(sayfalar) == 1
    for ad, df in list(sayfalar.items())[:max_sayfa]:
        metin = tablo_metne_cevir(df, max_satir=max_satir)
        if not metin:
            continue
        bloklar.append(metin if tek_sayfa else f"[Sayfa: {ad}]\n{metin}")
    if len(sayfalar) > max_sayfa:
        bloklar.append(f"(Not: dosyanın {len(sayfalar) - max_sayfa} sayfası "
                       f"bağlama sığmadığı için atlandı.)")
    return "\n\n".join(bloklar) if len(bloklar) > 1 else None


# --- Bilgi tabani (gecmis deneyler) ---------------------------------------
def load_knowledge_base():
    path = os.path.join("data", "test_learn_kb.csv")
    if not os.path.exists(path):
        return None
    kb = pd.read_csv(path)
    return "\n".join(kb_satirlarina_cevir(kb))


def yuklenen_dosyalar_hafizasi():
    """'Hafizada' isaretli dosyalarin metne cevrilmis hali."""
    meta = load_files_meta()
    bloklar = []
    for fid, bilgi in meta.items():
        if not bilgi.get("hafizada"):
            continue
        metin = dosya_metne_cevir(bilgi)
        if metin:
            bloklar.append(metin)
    return "\n\n".join(bloklar)


kb_text = load_knowledge_base()
dosya_text = yuklenen_dosyalar_hafizasi()
havuz_kumeleri = th.mevcut_kumeler()   # diskte bulunan veri kumeleri
havuz_df = th.birlesik_havuz()         # hepsinin Test_ID'ye gore tekil hali

# --- Oturum ilk kurulum ----------------------------------------------------
if "chats" not in st.session_state:
    st.session_state.chats = load_chats()
if "view" not in st.session_state:
    st.session_state.view = "chat"       # "chat" | "files" | "file" | "havuz"
if "active" not in st.session_state or st.session_state.active not in st.session_state.chats:
    if st.session_state.chats:
        st.session_state.active = list(st.session_state.chats.keys())[-1]
    else:
        new_chat()
if "active_file" not in st.session_state:
    st.session_state.active_file = None
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

files_meta = load_files_meta()

# --- Kenar cubugu: sohbetler + dosyalar + ayarlar -------------------------
with st.sidebar:
    if st.button("➕ Yeni sohbet", use_container_width=True):
        new_chat()
        st.rerun()

    st.markdown("**Sohbetler**")
    for cid in reversed(list(st.session_state.chats.keys())):
        baslik = st.session_state.chats[cid].get("title") or "Yeni sohbet"
        aktif = (cid == st.session_state.active
                 and st.session_state.view == "chat")
        etiket = ("🟢 " if aktif else "") + baslik[:32]
        if st.button(etiket, key=f"sw_{cid}", use_container_width=True):
            st.session_state.active = cid
            st.session_state.view = "chat"
            st.rerun()

    st.markdown("---")

    # --- TEST & LEARN HAVUZLARI ---------------------------------------
    st.markdown("**🛁 Banyo kategorisi & test havuzları**")
    if havuz_df is not None:
        if st.button("🧪 Test havuzları", use_container_width=True):
            st.session_state.view = "havuz"
            st.rerun()
        havuz_hafiza = st.radio(
            "Asistanın hafızası",
            ["Özet (önerilen)", "Tam (yönetici özeti + playbook)", "Kapalı"],
            key="havuz_hafiza",
            help="Özet: her testin hipotezi, ölçümü, öğrenimi ve tavsiyesi. "
                 "Tam: buna yönetici özeti ve 4 aşamalı uygulama planı da "
                 "eklenir (yanıtlar yavaşlar). Kapalı: havuz sohbete girmez.",
        )
    else:
        havuz_hafiza = "Kapalı"
        st.caption("Havuz bulunamadı (data/ klasörünü kontrol et).")

    st.markdown("---")

    # --- DOSYALARIM ---------------------------------------------------
    st.markdown("**📁 Dosyalarım**")
    if st.button("🗂️ Tüm dosyalar", use_container_width=True):
        st.session_state.view = "files"
        st.rerun()

    with st.expander("⬆️ Dosya yükle", expanded=not files_meta):
        kategori = st.selectbox(
            "Kategori",
            ["Test & Learn öğrenimleri", "Kampanya verisi", "Rapor / diğer"],
            key="up_kategori",
        )
        not_metni = st.text_input("Kısa not (opsiyonel)", key="up_not",
                                  placeholder="Örn: Eylül Meta kampanyası")
        yeni = st.file_uploader(
            "CSV veya Excel", type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
            key=f"file_up_{st.session_state.uploader_key}",
            label_visibility="collapsed",
        )
        if yeni:
            for u in yeni:
                save_uploaded_file(u, kategori=kategori, not_metni=not_metni)
            st.session_state.uploader_key += 1   # yukleyiciyi sifirla
            st.rerun()

    if files_meta:
        for fid, bilgi in reversed(list(files_meta.items())):
            aktif = (st.session_state.view == "file"
                     and st.session_state.active_file == fid)
            etiket = ("🟢 " if aktif else "📄 ") + bilgi["ad"][:28]
            if st.button(etiket, key=f"f_{fid}", use_container_width=True):
                st.session_state.view = "file"
                st.session_state.active_file = fid
                st.rerun()
    else:
        st.caption("Henüz dosya yok.")

    st.markdown("---")
    st.header("Ayarlar")
    api_key = os.environ.get("GOOGLE_API_KEY") or st.text_input(
        "Google API anahtarı", type="password",
        help="aistudio.google.com/apikey adresinden ücretsiz alabilirsin"
    )
    if kb_text:
        st.success(f"Bilgi tabanı: {kb_text.count(chr(10)) + 1} geçmiş deney")
    else:
        st.warning("Bilgi tabanı bulunamadı (data/test_learn_kb.csv).")
    if havuz_df is not None:
        marka_sayisi = (havuz_df["Brand"].nunique()
                        if "Brand" in havuz_df.columns else 0)
        kayip = 0
        if "Result" in havuz_df.columns:
            kayip = int((havuz_df["Result"].astype(str).str.upper()
                         == "LOSS").sum())
        ozet = (f"Test havuzu: {len(havuz_df)} tekil test / "
                f"{marka_sayisi} marka / {len(havuz_kumeleri)} dosya"
                + (f" ({kayip} kaybeden test dahil)" if kayip else ""))
        if havuz_hafiza == "Kapalı":
            st.caption(ozet + " — hafıza kapalı")
        else:
            st.success(ozet)
    if files_meta:
        hafizadaki = sum(1 for b in files_meta.values() if b.get("hafizada"))
        st.info(f"Dosyalarım: {len(files_meta)} dosya "
                f"({hafizadaki} tanesi asistanın hafızasında)")

# --- Asistan kimligi + hafiza ---------------------------------------------
havuz_text = (None if havuz_hafiza == "Kapalı"
              else th.kb_text(detay=havuz_hafiza.startswith("Tam")))

SYSTEM_PROMPT = (
    "Sen bir dijital pazarlama 'Test & Learn' asistanısın. Görevin: geçmiş "
    "test ve kampanya öğrenimlerine dayanarak yeni ürün/kampanyalar için "
    "stratejik, uygulanabilir öneriler vermek — kampanya kurgusu, hedef kitle "
    "optimizasyonu, platform seçimi, kreatif ve test tasarımı dahil.\n\n"
    "Kurallar:\n"
    "- Önerilerini mümkün olduğunca aşağıdaki geçmiş öğrenimlere DAYANDIR ve "
    "ilgili deney kodunu (örn. T004, VT001, GR002, REAL008) belirterek "
    "gerekçelendir.\n"
    "- İki ayrı hafızan var: (1) genel dijital pazarlama Test & Learn bilgi "
    "tabanı, (2) Test & Learn deney havuzu — banyo kategorisi (Vitra, Artema, "
    "İntema, Grohe, Hansgrohe, Duravit, Kohler) e-ticaret testleri + "
    "Meta/Google platform testleri + REAL### kodlu GERÇEK Eczacıbaşı Meta "
    "kampanyaları. Soru banyo/armatür/seramik/banyo mobilyası ya da bu "
    "markalarla ilgiliyse ÖNCE bu havuzu kullan; lift, p-value, örneklem ve "
    "güven değerlerini olduğu gibi aktar.\n"
    "- Kaynak hiyerarşisi: REAL### gerçek kampanya verisi > marka testleri > "
    "benchmark/mock. Bir testin 'Veri kaynağı' satırı benchmark/mock diyorsa "
    "bunu öneride açıkça belirt ve gerçek veriyle doğrulanmasını test "
    "önerisi olarak sun.\n"
    "- Havuzda sonucu LOSS olan KAYBEDEN testler var. Bunlar en değerli "
    "kısımdır: ilgili olduğunda 'şu denendi ve işe yaramadı' diye uyar, aynı "
    "hatayı tekrar önerme. Sadece kazanan testleri seçip anlatma.\n"
    "- Kullanıcının yüklediği gerçek dosyalar da hafızandadır; ilgili olduğunda "
    "hangi dosyadan geldiğini belirterek bunlara da atıf yap.\n"
    "- Sana metrik verilirse onlar koddan gelir, DOĞRUdur; sayı UYDURMA.\n"
    "- Önerileri hipotez olarak sun; belirsizlik varsa 'şunu test edelim' de.\n"
    "- Somut ol: bütçe mantığı, kitle, platform, kreatif ve ölçülecek metriği söyle.\n"
    "- Türkçe, net ve pratik yanıt ver.\n\n"
    "=== GEÇMİŞ TEST & LEARN HAFIZASI ===\n"
    f"{kb_text if kb_text else '(bilgi tabanı yüklenemedi)'}\n\n"
    "=== TEST & LEARN DENEY HAVUZU (banyo + platform + gerçek kampanyalar) ===\n"
    f"{havuz_text if havuz_text else '(havuz hafızada değil)'}\n\n"
    "=== KULLANICININ YÜKLEDİĞİ GERÇEK DOSYALAR ===\n"
    f"{dosya_text if dosya_text else '(yüklenmiş dosya yok)'}"
)


# --- Dosya sayfalari -------------------------------------------------------
def render_file_detail(fid):
    """Tek bir dosyanin detay ekrani: onizleme + metrikler + ayarlar."""
    bilgi = files_meta.get(fid)
    if not bilgi:
        st.warning("Dosya bulunamadı.")
        return

    ust = st.columns([6, 1])
    with ust[0]:
        st.title(f"📄 {bilgi['ad']}")
        st.caption(f"{bilgi.get('kategori', '-')} · yüklenme: "
                   f"{bilgi.get('tarih', '-')} · "
                   f"{round(bilgi.get('boyut', 0) / 1024, 1)} KB"
                   + (f" · {bilgi['not']}" if bilgi.get("not") else ""))
    with ust[1]:
        if st.button("⬅️ Sohbete dön", use_container_width=True):
            st.session_state.view = "chat"
            st.rerun()

    yol = file_path(bilgi)
    if os.path.exists(yol):
        with open(yol, "rb") as f:
            st.download_button("⬇️ İndir", f.read(), file_name=bilgi["ad"],
                               key=f"dl_{fid}")

    sayfalar = load_tables(bilgi)
    if not sayfalar:
        st.error("Dosya okunamadı (bozuk olabilir veya desteklenmeyen format).")
        df = None
    else:
        if len(sayfalar) > 1:
            # Cok sayfali Excel: hangi sayfayi inceleyecegini sec
            sayfa = st.selectbox(f"Sayfa ({len(sayfalar)} sayfa)",
                                 list(sayfalar.keys()), key=f"sh_{fid}")
            df = sayfalar[sayfa]
        else:
            df = next(iter(sayfalar.values()))

        st.markdown(f"**{len(df)} satır × {len(df.columns)} kolon**")
        st.dataframe(df, use_container_width=True, height=380)
        if th.is_test_table(df):
            st.info("Bu sayfa Test & Learn deney formatında — asistan lift, "
                    "p-value ve öğrenimleri doğrudan okuyabiliyor.")

        try:
            metrikler = compute_metrics(df)
            if any(v for v in metrikler.values()):
                st.subheader("Hesaplanan metrikler")
                st.dataframe(
                    pd.DataFrame(metrikler.items(),
                                 columns=["Metrik", "Değer"]),
                    hide_index=True, use_container_width=True,
                )
                if st.button("💬 Bu metrikleri sohbette kullan", key=f"use_{fid}"):
                    st.session_state["metrics_context"] = metrics_to_text(metrikler)
                    st.session_state.view = "chat"
                    st.rerun()
        except Exception:
            pass

    st.markdown("---")
    alt = st.columns([3, 1])
    with alt[0]:
        hafizada = st.checkbox(
            "Asistanın hafızasına dahil et (sohbetlerde bu veriyi kullansın)",
            value=bool(bilgi.get("hafizada")), key=f"kb_{fid}",
        )
        if hafizada != bool(bilgi.get("hafizada")):
            meta = load_files_meta()
            meta[fid]["hafizada"] = hafizada
            save_files_meta(meta)
            st.rerun()
    with alt[1]:
        if st.button("🗑️ Dosyayı sil", key=f"del_{fid}",
                     use_container_width=True):
            delete_file(fid)
            st.session_state.view = "files"
            st.session_state.active_file = None
            st.rerun()


def render_files_page():
    """Tum dosyalarin listelendigi ekran."""
    ust = st.columns([6, 1])
    with ust[0]:
        st.title("🗂️ Dosyalarım")
        st.caption("Gerçek Test & Learn öğrenimlerin ve kampanya verilerin "
                   "burada saklanır. Bir dosyaya tıklayıp içeriğini ve "
                   "metriklerini inceleyebilirsin.")
    with ust[1]:
        if st.button("⬅️ Sohbete dön", use_container_width=True):
            st.session_state.view = "chat"
            st.rerun()

    if not files_meta:
        st.info("Henüz dosya yüklenmemiş. Sol taraftaki **Dosyalarım → "
                "Dosya yükle** bölümünden CSV veya Excel yükleyebilirsin.")
        return

    ozet = pd.DataFrame([
        {
            "Dosya": b["ad"],
            "Kategori": b.get("kategori", "-"),
            "Not": b.get("not", ""),
            "Yüklenme": b.get("tarih", "-"),
            "Boyut (KB)": round(b.get("boyut", 0) / 1024, 1),
            "Hafızada": "✅" if b.get("hafizada") else "—",
        }
        for b in reversed(list(files_meta.values()))
    ])
    st.dataframe(ozet, hide_index=True, use_container_width=True)

    st.markdown("### Dosyayı aç")
    for fid, bilgi in reversed(list(files_meta.items())):
        satir = st.columns([5, 1])
        satir[0].markdown(f"**📄 {bilgi['ad']}** — {bilgi.get('kategori', '-')}"
                          f" · {bilgi.get('tarih', '-')}")
        if satir[1].button("Aç", key=f"open_{fid}", use_container_width=True):
            st.session_state.view = "file"
            st.session_state.active_file = fid
            st.rerun()


def _alan(r, kolon):
    """Detay ekraninda bir kolonu guvenli okur (bos/NaN ise None)."""
    deger = r.get(kolon)
    try:
        if deger is None or pd.isna(deger):
            return None
    except (TypeError, ValueError):
        pass
    metin = str(deger).strip()
    return metin if metin and metin.lower() != "nan" else None


def render_test_detay(r):
    """Tek bir testin tum alanlarini (kazanimlar dahil) ekrana yazar."""
    olcum = [f"**Ölçüm:** {_alan(r, 'Primary_Metric') or '-'}"]
    if _alan(r, "CR_Control") and _alan(r, "CR_Treatment"):
        olcum.append(f"kontrol {_alan(r, 'CR_Control')} → "
                     f"varyant {_alan(r, 'CR_Treatment')}")
    for etiket, kolon in (("p", "P_Value"), ("güven", "Confidence"),
                          ("örneklem", "Sample_Size"),
                          ("süre (gün)", "Test_Duration")):
        if _alan(r, kolon):
            olcum.append(f"{etiket}={_alan(r, kolon)}")
    st.markdown(", ".join(olcum))

    if _alan(r, "Control_Results") and _alan(r, "Treatment_Results"):
        ham = (f"**Ham sonuç:** kontrol {_alan(r, 'Control_Results')} → "
               f"varyant {_alan(r, 'Treatment_Results')}")
        if _alan(r, "Control_Reach") and _alan(r, "Treatment_Reach"):
            ham += (f" · erişim {_alan(r, 'Control_Reach')} → "
                    f"{_alan(r, 'Treatment_Reach')}")
        st.markdown(ham)

    if _alan(r, "Control_Version") or _alan(r, "Treatment_Version"):
        st.markdown(f"**Kontrol:** `{_alan(r, 'Control_Version') or '-'}`  \n"
                    f"**Varyant:** `{_alan(r, 'Treatment_Version') or '-'}`")

    for baslik, kolon in (("Kampanya amacı", "Campaign_Objective"),
                          ("Amaç", "Objective"),
                          ("Hipotez", "Hypothesis"),
                          ("Yan metrikler", "Secondary_Metrics")):
        if _alan(r, kolon):
            st.markdown(f"**{baslik}:** {_alan(r, kolon)}")

    # Kazanimlar — uzun metinler bloklar halinde
    for baslik, kolon in (("🎓 Öğrenim", "Key_Learnings"),
                          ("📈 İş etkisi", "Downstream_Impact"),
                          ("🧭 Yönetici özeti", "Executive_Summary"),
                          ("📌 Stratejik tavsiye", "Strategic_Recommendation"),
                          ("📋 Uygulama planı", "Implementation_Playbook"),
                          ("⚠️ Dikkat edilecekler", "Important_Cautions"),
                          ("💰 Beklenen getiri", "Expected_ROI")):
        if _alan(r, kolon):
            st.markdown(f"**{baslik}**")
            st.text(_alan(r, kolon))

    alt = []
    for baslik, kolon in (("Uygulama zorluğu", "Implementation_Difficulty"),
                          ("Benzer testler", "Similar_Tests"),
                          ("Veri kaynağı", "Data_Source")):
        if _alan(r, kolon):
            alt.append(f"{baslik}: {_alan(r, kolon)}")
    if alt:
        st.caption(" · ".join(alt))


def render_havuz_sekmesi(anahtar, df, kume_adi, aciklama):
    """Bir veri kumesinin sekmesi: filtre, ozet, grafik, tablo, detaylar."""
    st.markdown(aciklama)
    st.caption(f"Kaynak: `{th.VERI_KUMELERI[anahtar]['dosya']}` · "
               f"{len(df)} test × {len(df.columns)} kolon")

    # --- Filtreler (satir basina 3 kutu) ------------------------------
    filtreler = list(th.filtre_kolonlari(df).items())
    secimler = {}
    for bas in range(0, len(filtreler), 3):
        kutular = st.columns(3)
        for kutu, (etiket, kolon) in zip(kutular, filtreler[bas:bas + 3]):
            degerler = sorted(str(v) for v in df[kolon].dropna().unique())
            secimler[kolon] = kutu.multiselect(etiket, degerler,
                                               key=f"f_{anahtar}_{kolon}")

    min_lift = None
    if "Lift_Percent" in df.columns:
        lift_hepsi = pd.to_numeric(df["Lift_Percent"],
                                   errors="coerce").dropna()
        if len(lift_hepsi) and lift_hepsi.min() < lift_hepsi.max():
            min_lift = st.slider(
                "En az lift (%)", float(lift_hepsi.min()),
                float(lift_hepsi.max()), float(lift_hepsi.min()), step=1.0,
                key=f"f_{anahtar}_lift",
                help="Negatif değerler kaybeden testlerdir; onları da "
                     "görmek için soldan başlat.",
            )

    secili = th.filtrele(df, secimler, min_lift=min_lift)
    if secili.empty:
        st.warning("Bu filtrelerle eşleşen test yok.")
        return

    # --- Ozet kartlari ------------------------------------------------
    kartlar = th.ozet_kartlari(secili)
    kutular = st.columns(len(kartlar))
    for kutu, (etiket, deger) in zip(kutular, kartlar):
        kutu.metric(etiket, deger)

    # --- Grafikler ----------------------------------------------------
    if "Lift_Percent" in secili.columns and len(secili) > 1:
        lift = pd.to_numeric(secili["Lift_Percent"], errors="coerce")
        grafik = st.columns(2)
        for kutu, kolon, baslik in (
            (grafik[0], "Test_Type", "Test tipine göre ortalama lift (%)"),
            (grafik[1], "Brand", "Markaya göre ortalama lift (%)"),
        ):
            if kolon in secili.columns:
                kutu.markdown(f"**{baslik}**")
                kutu.bar_chart(secili.assign(_lift=lift)
                                     .groupby(kolon)["_lift"].mean()
                                     .sort_values(ascending=False))

    # --- Tablo --------------------------------------------------------
    gosterilecek = [k for k in th.TABLO_KOLONLARI if k in secili.columns]
    st.markdown(f"**{len(secili)} test**")
    st.dataframe(secili[gosterilecek] if gosterilecek else secili,
                 hide_index=True, use_container_width=True, height=340)

    # --- Sohbete tasima ----------------------------------------------
    islem = st.columns([2, 2, 4])
    if islem[0].button("💬 Bu testleri sohbette kullan", type="primary",
                       use_container_width=True, key=f"kul_{anahtar}"):
        st.session_state["havuz_secim_context"] = th.secim_metni(
            secili, kume_adi=kume_adi)
        st.session_state.view = "chat"
        st.rerun()
    if islem[1].button("🧹 Seçimi temizle", use_container_width=True,
                       key=f"tmz_{anahtar}"):
        st.session_state.pop("havuz_secim_context", None)
        st.rerun()

    # --- Test detaylari (ogrenim / kazanimlar) ------------------------
    st.markdown("### Testler ve kazanımlar")
    for _, r in secili.iterrows():
        lift = pd.to_numeric(r.get("Lift_Percent"), errors="coerce")
        sonuc = str(r.get("Result", "")).upper()
        isaret = "🔴" if sonuc == "LOSS" else "🟢"
        etiket = (f"{isaret} {r.get('Test_ID', '?')} · {r.get('Brand', '-')} · "
                  f"{r.get('Test_Name', '-')}")
        if pd.notna(lift):
            etiket += f"  ({lift:+.1f}%)"
        with st.expander(etiket):
            render_test_detay(r)

    # --- Excel'in diger (ozet) sayfalari ------------------------------
    sayfalar = th.load_sheets(anahtar)
    digerleri = {ad: tablo for ad, tablo in sayfalar.items()
                 if ad != th.VERI_KUMELERI[anahtar].get("sayfa")}
    if digerleri:
        with st.expander("📑 Excel'in diğer sayfaları (özet tablolar)"):
            sayfa = st.selectbox("Sayfa", list(digerleri.keys()),
                                 key=f"sayfa_{anahtar}")
            st.dataframe(digerleri[sayfa], hide_index=True,
                         use_container_width=True)


def render_havuz_page():
    """Test & Learn havuzlari: her veri kumesi kendi sekmesinde."""
    ust = st.columns([6, 1])
    with ust[0]:
        st.title("🧪 Test & Learn havuzları")
        st.caption("Her sekme bir veri dosyası. Filtreleyip inceleyebilir, "
                   "seçtiğin testleri sohbete bağlam olarak taşıyabilirsin.")
    with ust[1]:
        if st.button("⬅️ Sohbete dön", use_container_width=True):
            st.session_state.view = "chat"
            st.rerun()

    if not havuz_kumeleri:
        st.error("Hiçbir test veri kümesi bulunamadı. `data/` klasöründeki "
                 "dosyaları kontrol et.")
        return

    if havuz_df is not None:
        st.info(f"Bu dosyalar iç içe geçmiştir (aynı test birden fazla "
                f"dosyada olabilir). Asistanın hafızasına Test_ID'ye göre "
                f"**tekilleştirilmiş {len(havuz_df)} test** gider — aynı "
                f"deney modele birden fazla kez verilmez.")

    sekmeler = st.tabs([
        f"{th.VERI_KUMELERI[a]['sekme']} ({len(th.load_dataset(a))})"
        for a in havuz_kumeleri
    ])
    for sekme, anahtar in zip(sekmeler, havuz_kumeleri):
        with sekme:
            render_havuz_sekmesi(
                anahtar, th.load_dataset(anahtar),
                kume_adi=th.VERI_KUMELERI[anahtar]["sekme"],
                aciklama=th.VERI_KUMELERI[anahtar]["aciklama"],
            )


# --- Modelden yanit alma (yeniden deneme + yedek model) -------------------
def _hata_tipi(mesaj):
    """Hata metnine bakip tur belirler: 'mesgul' / 'kota' / 'anahtar' / 'diger'."""
    m = mesaj.upper()
    if any(k in m for k in ("503", "UNAVAILABLE", "OVERLOADED", "500",
                            "INTERNAL", "502", "504", "DEADLINE")):
        return "mesgul"
    if any(k in m for k in ("429", "RESOURCE_EXHAUSTED", "QUOTA")):
        return "kota"
    if any(k in m for k in ("API_KEY", "API KEY", "401", "403",
                            "PERMISSION_DENIED", "UNAUTHENTICATED")):
        return "anahtar"
    return "diger"


def build_contents(chat):
    """Sohbet gecmisini modelin bekledigi formata cevirir."""
    metrics_ctx = st.session_state.get("metrics_context")
    secim_ctx = st.session_state.get("havuz_secim_context")
    contents = []
    for i, m in enumerate(chat["messages"]):
        role = "user" if m["role"] == "user" else "model"
        text = m["content"]
        if role == "user" and i == len(chat["messages"]) - 1:
            # Son soruya, ekranda hazirlanan baglami eklyoruz
            onek = []
            if metrics_ctx:
                onek.append(f"[Yüklenen kampanya metrikleri:\n{metrics_ctx}]")
            if secim_ctx:
                onek.append(f"[Ekranda seçilen testler:\n{secim_ctx}]")
            if onek:
                text = "\n\n".join(onek) + "\n\n" + text
        contents.append({"role": role, "parts": [{"text": text}]})
    return contents


def yanit_uret(chat, api_key):
    """
    Modelden yanit alir. Model mesgulse (503) bekleyip tekrar dener,
    olmazsa yedek modellere gecer. (yanit, hata_tipi, ham_hata) doner.
    """
    contents = build_contents(chat)
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        return None, "anahtar", str(e)

    son_hata, son_tip = "", "diger"
    for model_adi in MODELLER:
        for deneme in range(DENEME_SAYISI):
            try:
                response = client.models.generate_content(
                    model=model_adi,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        max_output_tokens=8000,
                    ),
                )
                answer = (response.text or "").strip()
                if answer:
                    return answer, None, None
                son_hata, son_tip = "Model boş yanıt döndü.", "diger"
                break  # bos yanit: bu modelde israr etme, digerine gec
            except Exception as e:
                son_hata = str(e)
                son_tip = _hata_tipi(son_hata)
                if son_tip == "anahtar":
                    return None, son_tip, son_hata      # denemeye gerek yok
                if son_tip in ("mesgul", "kota") and deneme < DENEME_SAYISI - 1:
                    time.sleep(2 * (deneme + 1))        # 2sn, 4sn bekle
                    continue
                break  # bu modelden vazgec, sonraki modeli dene
    return None, son_tip, son_hata


def hata_mesaji(tip):
    if tip == "mesgul":
        return ("⏳ Google'ın modeli şu anda çok yoğun (503). Birkaç saniye "
                "bekleyip **🔄 Tekrar dene**'ye bas — sohbetin ve yazdığın "
                "soru duruyor, kaybolmadı.")
    if tip == "kota":
        return ("🚦 Ücretsiz kullanım kotan (dakikalık/günlük limit) dolmuş "
                "görünüyor. Biraz bekleyip **🔄 Tekrar dene**'ye basabilirsin.")
    if tip == "anahtar":
        return ("🔑 API anahtarı geçersiz ya da yetkisiz. `.env` dosyasındaki "
                "`GOOGLE_API_KEY` değerini kontrol et "
                "(aistudio.google.com/apikey).")
    return ("⚠️ Yanıt alınamadı. **🔄 Tekrar dene**'ye basabilir ya da soruyu "
            "biraz kısaltıp tekrar sorabilirsin.")


def render_chat():
    st.title("🧪 Digital Marketing Test & Learn")
    st.caption("Geçmiş test öğrenimlerine dayanarak kampanya, hedef kitle ve "
               "optimizasyon önerileri veren AI pazarlama asistanı.")

    # --- Veri yukleme (OPSIYONEL, tek seferlik metrik hesaplama) ----------
    with st.expander("📎 (Opsiyonel) Kampanya verisi yükle — metrikleri hesaplayayım"):
        uploaded = st.file_uploader(
            "CSV veya Excel", type=["csv", "xlsx", "xls"],
            label_visibility="collapsed", key="chat_uploader"
        )
        if uploaded is not None:
            if uploaded.name.lower().endswith(".csv"):
                df = pd.read_csv(uploaded)
            else:
                df = pd.read_excel(uploaded)
            st.dataframe(df.head())
            metrics = compute_metrics(df)
            st.dataframe(
                pd.DataFrame(metrics.items(), columns=["Metrik", "Değer"]),
                hide_index=True,
            )
            st.session_state["metrics_context"] = metrics_to_text(metrics)
            if st.button("📁 Bu dosyayı Dosyalarım'a kalıcı olarak kaydet"):
                save_uploaded_file(uploaded, kategori="Kampanya verisi")
                st.success("Dosyalarım'a kaydedildi.")
                st.rerun()

    # --- Ekrandan tasinan test secimi varsa gosterelim -------------------
    if st.session_state.get("havuz_secim_context"):
        satir = st.columns([5, 1])
        satir[0].info("🧪 Havuzdan seçtiğin testler sorularına ek bağlam "
                      "olarak veriliyor.")
        if satir[1].button("Kaldır", use_container_width=True):
            st.session_state.pop("havuz_secim_context", None)
            st.rerun()

    st.markdown("---")
    chat = st.session_state.chats[st.session_state.active]

    for msg in chat["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input(
        "Örn: Elimizde yeni bir vitamin ürünü var, satışı artırmak için nasıl bir kampanya kurmalıyız?"
    )

    if user_input:
        chat["messages"].append({"role": "user", "content": user_input})
        if not chat.get("title") or chat["title"] == "Yeni sohbet":
            chat["title"] = user_input[:40]
        save_chats(st.session_state.chats)
        st.rerun()   # mesaj gecmise yazildi; yanit asagida uretilir

    # --- Cevap bekleyen bir soru varsa yanit uret -------------------------
    # (yanit alinamazsa soru gecmiste kalir; "Tekrar dene" ile yeniden denenir)
    if chat["messages"] and chat["messages"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            if not api_key:
                st.warning("Önce .env dosyasına ya da kenar çubuğuna "
                           "API anahtarını gir.")
            else:
                with st.spinner("Geçmiş öğrenimlere bakıyor..."):
                    answer, hata_tip, ham_hata = yanit_uret(chat, api_key)

                if answer:
                    st.markdown(answer)
                    chat["messages"].append({"role": "assistant",
                                             "content": answer})
                    save_chats(st.session_state.chats)
                else:
                    st.error(hata_mesaji(hata_tip))
                    kol = st.columns([1, 1, 4])
                    if kol[0].button("🔄 Tekrar dene", type="primary"):
                        st.rerun()
                    if kol[1].button("🗑️ Soruyu geri al"):
                        chat["messages"].pop()
                        save_chats(st.session_state.chats)
                        st.rerun()
                    if ham_hata:
                        with st.expander("Teknik detay"):
                            st.code(ham_hata)


# --- Yonlendirme (hangi ekran gosterilecek) --------------------------------
if st.session_state.view == "files":
    render_files_page()
elif st.session_state.view == "havuz":
    render_havuz_page()
elif st.session_state.view == "file" and st.session_state.active_file:
    render_file_detail(st.session_state.active_file)
else:
    render_chat()
#python -m streamlit run app.py