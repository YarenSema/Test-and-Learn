"""
test_havuzu.py
--------------
Test & Learn veri kumelerini okuyan, ekrana ve asistanin hafizasina
hazirlayan katman. (Onceki adi: bathroom_kb.py)

Su anda uc veri kumesi var ve BUNLAR IC ICE GECMISTIR:

    Banyo (35 test)  ⊂  Zenginlestirilmis (43 test)  ⊂  Master (58 test)

  - data/Bathroom_Category_Test_Learn_MEGA.xlsx      -> 35 banyo e-ticaret testi
  - data/Test_Learn_Database_ENRICHED_43_Tests.csv   -> + Meta/Google platform
                                                        testleri, ROI ve zorluk
                                                        kolonlari
  - data/Test_Learn_Database_MASTER_58_Tests_COMPLETE.csv
        -> + 15 GERCEK Eczacibasi Meta kampanyasi (REAL###). Bu kumede
           KAYBEDEN (LOSS) testler de var; onlar da birer ogrenimdir.

Bu yuzden:
  * EKRANDA her dosya kendi sekmesinde ayri ayri gosterilir (kullanici hangi
    dosyada ne var gormek ister).
  * HAFIZADA ise tek bir birlesik havuz kullanilir (birlesik_havuz): ayni
    test uc kez modele gitmesin diye Test_ID'ye gore tekillestirilir ve
    dosyalarin birbirinde olmayan kolonlari (Expected_ROI, Similar_Tests...)
    birlestirilir.

ONEMLI: metrics.py'deki kural burada da gecerli — lift, p-value, orneklem
gibi sayilar dosyadan/koddan gelir, modele hesaplatilmaz.
"""

import os

import pandas as pd
import streamlit as st

DATA_DIR = "data"

# Ekrandaki sekme sirasi ve her veri kumesinin tanimi
VERI_KUMELERI = {
    "banyo": {
        "sekme": "🛁 Banyo kategorisi",
        "dosya": os.path.join(DATA_DIR,
                              "Bathroom_Category_Test_Learn_MEGA.xlsx"),
        "sayfa": "All Tests (Detailed)",
        "aciklama": "Vitra, Artema, İntema, Grohe, Hansgrohe, Duravit ve "
                    "Kohler markalarının banyo kategorisi e-ticaret testleri "
                    "(PDP, Checkout, Email, Cart, Category).",
    },
    "master": {
        "sekme": "📚 Master veritabanı",
        "dosya": os.path.join(DATA_DIR,
                              "Test_Learn_Database_MASTER_58_Tests_COMPLETE.csv"),
        "sayfa": None,
        "aciklama": "En geniş havuz: banyo testleri + Meta/Google platform "
                    "testleri + **15 gerçek Eczacıbaşı Meta kampanyası "
                    "(REAL###)**. Kaybeden (LOSS) testler de burada — "
                    "neyin işe yaramadığı en az kazanan testler kadar "
                    "değerli.",
    },
    "enriched": {
        "sekme": "✨ Zenginleştirilmiş",
        "dosya": os.path.join(DATA_DIR,
                              "Test_Learn_Database_ENRICHED_43_Tests.csv"),
        "sayfa": None,
        "aciklama": "43 kazanan test; her biri yönetici özeti, stratejik "
                    "tavsiye, beklenen getiri, uygulama zorluğu ve benzer "
                    "test önerileriyle birlikte.",
    },
}
SIRA = ["banyo", "master", "enriched"]

# Bir tablonun "deney havuzu" formatinda olup olmadigini anlamak icin
# aranan kolonlar (kucuk harfe cevrilerek kontrol edilir).
TEST_KOLONLARI = ["test_id", "test_name", "brand", "test_type",
                  "primary_metric", "lift_percent", "key_learnings"]

# Ekranda filtre olarak sunulacak kolonlar (etiket -> kolon adi).
# Tabloda olmayan kolonlar otomatik atlanir.
FILTRE_ADAYLARI = {
    "Marka": "Brand",
    "Ülke": "Country",
    "Ürün kategorisi": "Product_Category",
    "Test tipi": "Test_Type",
    "Kampanya amacı": "Campaign_Objective",
    "Sonuç": "Result",
}

# Ekranda tabloda gosterilecek kolon sirasi
TABLO_KOLONLARI = ["Test_ID", "Brand", "Country", "Product_Category",
                   "Test_Type", "Campaign_Objective", "Primary_Metric",
                   "CR_Control", "CR_Treatment", "Lift_Percent", "P_Value",
                   "Confidence", "Sample_Size", "Result", "Launch_Date",
                   "Data_Source"]


# --- Okuma ----------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _oku(path, mtime, sayfa):
    """CSV ya da Excel sayfasini okur. mtime sadece cache anahtaridir."""
    try:
        if path.lower().endswith(".csv"):
            for kodlama in ("utf-8", "utf-8-sig", "cp1254", "latin-1"):
                try:
                    return pd.read_csv(path, encoding=kodlama)
                except UnicodeDecodeError:
                    continue
            return None
        return pd.read_excel(path, sheet_name=sayfa or 0)
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def _excel_sayfalari(path, mtime):
    """Excel'deki TUM sayfalari okur (banyo dosyasinin ozet sayfalari icin)."""
    try:
        return pd.read_excel(path, sheet_name=None)
    except Exception:
        return {}


def load_dataset(anahtar):
    """Bir veri kumesini tablo olarak getirir (yoksa None)."""
    tanim = VERI_KUMELERI.get(anahtar)
    if not tanim or not os.path.exists(tanim["dosya"]):
        return None
    df = _oku(tanim["dosya"], os.path.getmtime(tanim["dosya"]), tanim["sayfa"])
    if df is None or df.empty:
        return None
    return df


def mevcut_kumeler():
    """Diskte gercekten bulunan veri kumelerinin anahtarlari (sirali)."""
    return [a for a in SIRA if load_dataset(a) is not None]


def load_sheets(anahtar):
    """Excel veri kumesinin diger (ozet) sayfalari."""
    tanim = VERI_KUMELERI.get(anahtar) or {}
    yol = tanim.get("dosya", "")
    if not yol.lower().endswith((".xlsx", ".xls")) or not os.path.exists(yol):
        return {}
    return _excel_sayfalari(yol, os.path.getmtime(yol))


def is_test_table(df):
    """Tablo, Test & Learn deney formatinda mi?"""
    if df is None or getattr(df, "empty", True):
        return False
    kolonlar = [str(c).strip().lower() for c in df.columns]
    return all(k in kolonlar for k in TEST_KOLONLARI)


# --- Birlesik havuz (hafiza icin tekillestirme) ---------------------------
def _tamamla(df, ek):
    """ek tablodaki kolonlari/degerleri Test_ID uzerinden df'e tasir."""
    if ek is None or "Test_ID" not in ek.columns or "Test_ID" not in df.columns:
        return df
    ek = ek.drop_duplicates("Test_ID").set_index("Test_ID")
    for kolon in ek.columns:
        esleme = ek[kolon]
        if kolon not in df.columns:
            df[kolon] = df["Test_ID"].map(esleme)
        else:
            bos = df[kolon].isna()
            if bos.any():
                df.loc[bos, kolon] = df.loc[bos, "Test_ID"].map(esleme)
    return df


def birlesik_havuz():
    """
    Tum veri kumelerini Test_ID'ye gore tekillestirip tek tabloda birlestirir.
    En genis kume temel alinir, digerlerinden sadece EKSIK test ve kolonlar
    eklenir. Hafizaya (SYSTEM_PROMPT) bu tablo gider.
    """
    kumeler = [(a, load_dataset(a)) for a in ("master", "enriched", "banyo")]
    kumeler = [(a, d) for a, d in kumeler if d is not None]
    if not kumeler:
        return None

    # en cok satiri olan kumeyi temel al
    kumeler.sort(key=lambda x: len(x[1]), reverse=True)
    df = kumeler[0][1].copy()

    for _, ek in kumeler[1:]:
        if "Test_ID" in df.columns and "Test_ID" in ek.columns:
            eksik = ek[~ek["Test_ID"].isin(df["Test_ID"])]
            if len(eksik):
                df = pd.concat([df, eksik], ignore_index=True)
    for _, ek in kumeler[1:]:
        df = _tamamla(df, ek)
    return df


# --- Deneyleri metne cevirme ---------------------------------------------
def _temiz(deger, kirp=None):
    """Cok satirli/sussu metni tek satira indirger."""
    metin = " ".join(str(deger).split())
    if kirp and len(metin) > kirp:
        metin = metin[:kirp].rstrip() + "…"
    return metin


def _deger(satir, kolon, yoksa="-"):
    """Satirdan guvenli deger okur (kolon yok / bos ise 'yoksa' doner)."""
    if kolon not in satir.index:
        return yoksa
    deger = satir[kolon]
    try:
        if pd.isna(deger):
            return yoksa
    except (TypeError, ValueError):
        pass
    metin = _temiz(deger)
    return metin if metin and metin.lower() != "nan" else yoksa


def _sayi(satir, kolon):
    """Sayisal deger okur (okunamazsa None)."""
    try:
        deger = pd.to_numeric(satir.get(kolon), errors="coerce")
        return None if pd.isna(deger) else float(deger)
    except Exception:
        return None


def _satir_metni(r, detay=False):
    """Tek bir deneyi asistanin okuyacagi bloga cevirir (r: kucuk harf indeks)."""
    lift = _sayi(r, "lift_percent")
    kontrol = _sayi(r, "cr_control")
    varyant = _sayi(r, "cr_treatment")

    olcum = [f"Ölçülen metrik: {_deger(r, 'primary_metric')}"]
    if kontrol is not None and varyant is not None:
        olcum.append(f"kontrol {kontrol:g} → varyant {varyant:g}")
    if lift is not None:
        olcum.append(f"lift {lift:+.1f}%")
    pdeger = _sayi(r, "p_value")
    if pdeger is not None:
        olcum.append(f"p={pdeger:g}")
    guven = _deger(r, "confidence", "")
    if guven:
        olcum.append(f"güven {guven}")
    orneklem = _sayi(r, "sample_size")
    if orneklem is not None:
        olcum.append(f"örneklem {int(orneklem)}")
    sure = _sayi(r, "test_duration")
    if sure is not None:
        olcum.append(f"süre {int(sure)} gün")

    sonuc = _deger(r, "result", "")
    if sonuc.upper() == "LOSS":
        olcum.append("sonuç LOSS (KAYBEDEN TEST — bu da bir öğrenim, "
                     "aynı hatayı önermemek için kullan)")
    elif sonuc:
        olcum.append(f"sonuç {sonuc}")

    parca = [
        f"[{_deger(r, 'test_id')} · {_deger(r, 'brand')} · "
        f"{_deger(r, 'country')} · {_deger(r, 'product_category')} · "
        f"{_deger(r, 'test_type')} testi] {_deger(r, 'test_name')}",
    ]
    for etiket, kolon in (("Kampanya amacı", "campaign_objective"),
                          ("Amaç", "objective"),
                          ("Hipotez", "hypothesis")):
        deger = _deger(r, kolon, "")
        if deger:
            parca.append(f"{etiket}: {deger}")

    parca.append(" | ".join(olcum))

    yan = _deger(r, "secondary_metrics", "")
    if yan:
        parca.append(f"Yan metrikler: {yan}")

    kv = _deger(r, "control_version", "")
    tv = _deger(r, "treatment_version", "")
    if kv or tv:
        parca.append(f"Kontrol versiyonu: {kv or '-'} || "
                     f"Varyant versiyonu: {tv or '-'}")

    ks = _sayi(r, "control_results")
    ts = _sayi(r, "treatment_results")
    kr = _sayi(r, "control_reach")
    tr = _sayi(r, "treatment_reach")
    if ks is not None and ts is not None:
        ham = f"Ham sonuç: kontrol {ks:g} → varyant {ts:g}"
        if kr is not None and tr is not None:
            ham += f" | erişim {kr:g} → {tr:g}"
        parca.append(ham)

    for etiket, kolon in (("Öğrenim", "key_learnings"),
                          ("İş etkisi", "downstream_impact"),
                          ("Stratejik tavsiye", "strategic_recommendation"),
                          ("Dikkat edilecekler", "important_cautions")):
        deger = _deger(r, kolon, "")
        if deger:
            parca.append(f"{etiket}: {deger}")

    ek = []
    for etiket, kolon in (("Beklenen getiri", "expected_roi"),
                          ("Uygulama zorluğu", "implementation_difficulty"),
                          ("Benzer testler", "similar_tests")):
        deger = _deger(r, kolon, "")
        if deger:
            ek.append(f"{etiket}: {_temiz(deger, 260)}")
    if ek:
        parca.append(" | ".join(ek))

    if detay:
        for etiket, kolon in (("Yönetici özeti", "executive_summary"),
                              ("Uygulama planı", "implementation_playbook")):
            deger = _deger(r, kolon, "")
            if deger:
                parca.append(f"{etiket}: {deger}")

    parca.append(f"Veri kaynağı: {_deger(r, 'data_source')}")
    return "\n".join(parca)


def test_satirlari(df, detay=False):
    """Deney tablosunu asistanin okuyacagi satirlara cevirir."""
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return [_satir_metni(r, detay=detay) for _, r in df.iterrows()]


def _ozet_metni(df):
    """Marka / test tipi / sonuc bazinda ozet satirlari (koddan hesaplanir)."""
    if "Lift_Percent" not in df.columns:
        return []

    lift = pd.to_numeric(df["Lift_Percent"], errors="coerce")
    bloklar = []

    if "Result" in df.columns:
        sayim = df["Result"].astype(str).str.upper().value_counts()
        bloklar.append("-- Sonuç dağılımı --\n" + ", ".join(
            f"{ad}: {adet} test" for ad, adet in sayim.items()))

    for etiket, kolon in (("Marka", "Brand"), ("Test tipi", "Test_Type"),
                          ("Ürün kategorisi", "Product_Category")):
        if kolon not in df.columns:
            continue
        ozet = (df.assign(_lift=lift)
                  .groupby(kolon)["_lift"]
                  .agg(["count", "mean", "max"])
                  .sort_values("mean", ascending=False))
        satirlar = [f"-- {etiket} bazında ortalama etki --"]
        for ad, s in ozet.iterrows():
            if pd.isna(s["mean"]):
                satirlar.append(f"{ad}: {int(s['count'])} test")
            else:
                satirlar.append(f"{ad}: {int(s['count'])} test, "
                                f"ort. lift {s['mean']:+.1f}%, "
                                f"en yüksek {s['max']:+.1f}%")
        bloklar.append("\n".join(satirlar))
    return bloklar


def kb_text(detay=False, max_test=None):
    """
    Birlesik havuzun tamamini SYSTEM_PROMPT'a konacak metne cevirir.
    detay=True ise yonetici ozeti ve uygulama planlari da eklenir (uzun).
    Havuz yoksa None doner.
    """
    df = birlesik_havuz()
    if df is None:
        return None

    kaynaklar = [os.path.basename(VERI_KUMELERI[a]["dosya"])
                 for a in mevcut_kumeler()]
    kapsam = [f"Toplam {len(df)} tekil test"]
    for etiket, kolon in (("Marka", "Brand"), ("Ülke", "Country"),
                          ("Test tipi", "Test_Type")):
        if kolon in df.columns:
            degerler = [str(v) for v in df[kolon].dropna().unique()]
            kapsam.append(f"{etiket}: {', '.join(degerler)}")

    parcalar = [
        "Kaynak dosyalar: " + ", ".join(kaynaklar) +
        " (aynı test birden fazla dosyada olabilir; burada Test_ID'ye göre "
        "tekilleştirildi)",
        " | ".join(kapsam),
        "Not: Havuzdaki testlerin bir kısmı sektör benchmark'ı / simülasyon, "
        "bir kısmı (REAL### kodlular) GERÇEK Eczacıbaşı Meta kampanya "
        "verisidir — her deneyin 'Veri kaynağı' satırına bak ve öneri "
        "verirken bunu belirt. Sonucu LOSS olan testler kaybeden testlerdir; "
        "onları 'şunu yapmayın / şu koşulda işe yaramadı' diye kullan.",
    ]
    parcalar += _ozet_metni(df)

    satirlar = test_satirlari(df, detay=detay)
    if max_test:
        satirlar = satirlar[:max_test]
    parcalar.append("-- TESTLER --")
    parcalar.append("\n\n".join(satirlar))
    return "\n\n".join(parcalar)


# --- Ekran icin yardimcilar ----------------------------------------------
def filtre_kolonlari(df):
    """Bu tabloda gercekten bulunan filtre kolonlari (etiket -> kolon)."""
    return {etiket: kolon for etiket, kolon in FILTRE_ADAYLARI.items()
            if kolon in df.columns and df[kolon].notna().any()}


def filtrele(df, secimler, min_lift=None):
    """
    secimler: {kolon adi: [secili degerler]} — bos liste = filtre yok.
    min_lift: verilirse Lift_Percent bu degerin altindaki testleri atar.
    """
    sonuc = df
    for kolon, degerler in secimler.items():
        if degerler and kolon in sonuc.columns:
            sonuc = sonuc[sonuc[kolon].astype(str).isin(degerler)]
    if min_lift is not None and "Lift_Percent" in sonuc.columns:
        lift = pd.to_numeric(sonuc["Lift_Percent"], errors="coerce")
        sonuc = sonuc[lift.fillna(-1e9) >= min_lift]
    return sonuc


def ozet_kartlari(df):
    """Ekrandaki metrik kartlari icin (etiket, deger) listesi."""
    kartlar = [("Test sayısı", str(len(df)))]
    if not len(df):
        return kartlar

    if "Result" in df.columns:
        sonuclar = df["Result"].astype(str).str.upper()
        kazanan = int((sonuclar == "WIN").sum())
        kaybeden = int((sonuclar == "LOSS").sum())
        if kazanan or kaybeden:
            kartlar.append(("Kazanan / kaybeden", f"{kazanan} / {kaybeden}"))

    if "Lift_Percent" in df.columns:
        lift = pd.to_numeric(df["Lift_Percent"], errors="coerce").dropna()
        if len(lift):
            kartlar.append(("Ortalama lift", f"{lift.mean():+.1f}%"))
            kartlar.append(("En yüksek lift", f"{lift.max():+.1f}%"))
            kartlar.append((">%30 etki", f"{int((lift > 30).sum())} test"))
    if "Sample_Size" in df.columns:
        n = pd.to_numeric(df["Sample_Size"], errors="coerce").dropna()
        if len(n):
            kartlar.append(("Ortalama örneklem",
                            f"{int(n.mean()):,}".replace(",", ".")))
    return kartlar


def secim_metni(df, kume_adi="", max_test=25):
    """Ekranda filtrelenmis testleri sohbete baglam olarak vermek icin."""
    if df is None or df.empty:
        return ""
    satirlar = test_satirlari(df.head(max_test))
    baslik = (f"{kume_adi + ' havuzundan ' if kume_adi else ''}"
              f"seçilen {len(satirlar)} test (toplam {len(df)} eşleşme):")
    return baslik + "\n\n" + "\n\n".join(satirlar)
