"""
ekip_testleri.py — ekibin uygulamaya girdigi testler (aktif + biten)
--------------------------------------------------------------------
Testler depo.py uzerinden (Supabase ayarliysa bulutta) tutulur. Bu modul:
  * sayisal sonuc alanlarini okur (Turkce "0,90" / "7.102" yazimlari dahil),
  * lift'i havuzun kuraliyla hesaplar (pozitif = iyilesme, maliyet
    metriklerinde de),
  * testleri Test & Learn havuzunun kolon formatina cevirir (filtre, grafik,
    "sohbette kullan" ayni kodla calissin diye),
  * asistanin okuyacagi metni uretir.
"""
import re

import pandas as pd

import test_havuzu as th

# Kayitta Ingilizce kod durur (havuz dosyalariyla ayni), ekranda Turkce etiket
SONUCLAR = {
    "": "— (henüz belli değil)",
    "WIN": "🟢 Kazandı",
    "LOSS": "🔴 Kaybetti",
    "INCONCLUSIVE": "⚪ Anlamlı fark yok",
}

TEST_TIPLERI = ["", "Kreatif", "Metin / mesaj", "Hedef kitle",
                "Kampanya kurgusu", "Ürün seti / katalog", "Teklif / bütçe",
                "Landing page", "PDP", "Category", "Cart", "Checkout", "Email",
                "Diğer"]

# Sunum slaytindaki iki karsilastirma kutusunun alanlari
KUTU_ALANLARI = ("ad", "alt", "detay", "deger1", "etiket1", "deger2",
                 "etiket2", "not")


def test_kodu(tid):
    """Havuzdaki Test_ID'lerle karismayan kisa kod."""
    return "EK-" + str(tid)[:6].upper()


def sayi(metin):
    """
    "0,90" / "4.42" / "7.102,5" / "%12" / "1 250" gibi yazimlari sayiya cevirir.
    Tek nokta ondalik kabul edilir (oranlar 0.043 gibi yazildigi icin);
    birden fazla nokta binlik ayiricidir. Okunamazsa None.
    """
    if metin is None:
        return None
    if isinstance(metin, (int, float)):
        return None if pd.isna(metin) else float(metin)
    s = re.sub(r"[^\d,.\-]", "", str(metin).replace("−", "-"))
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):          # 7.102,5
            s = s.replace(".", "").replace(",", ".")
        else:                                    # 7,102.5
            s = s.replace(",", "")
    elif "," in s:
        s = (s.replace(",", "") if s.count(",") > 1 else s.replace(",", "."))
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def bicim(x, ondalik=2):
    """Sayiyi gereksiz sifirlar olmadan yazar (None -> '')."""
    if x is None:
        return ""
    metin = f"{x:,.{ondalik}f}".rstrip("0").rstrip(".")
    return metin.replace(",", " ")


def lift_hesapla(b):
    """
    Elle girilen lift varsa o; yoksa kontrol/varyanttan iyilesme yuzdesi.
    Maliyet metriklerinde (CPC, CPA...) degerin dusmesi iyilesmedir.
    """
    elle = sayi(b.get("lift"))
    if elle is not None:
        return elle
    kontrol, varyant = sayi(b.get("kontrol_deger")), sayi(b.get("varyant_deger"))
    if kontrol in (None, 0) or varyant is None:
        return None
    degisim = (varyant - kontrol) / abs(kontrol) * 100
    if th._maliyet_metrigi(b.get("metrik", "")):
        degisim = -degisim
    return round(degisim, 1)


def kutular(b):
    """Sunum icin girilmis karsilastirma kutulari (bos olanlar atilir)."""
    sonuc = []
    for k in (b.get("kutular") or [])[:2]:
        k = {a: str(k.get(a, "") or "").strip() for a in KUTU_ALANLARI}
        if any(k.values()):
            sonuc.append(k)
    return sonuc


# --- Havuz formati ----------------------------------------------------------
def havuz_tablosu(testler):
    """
    {tid: bilgi} -> Test & Learn havuz kolonlarinda tablo (en yeni ustte).
    Bos kayit icin bos (kolonlu) tablo doner.
    """
    satirlar = []
    for tid, b in reversed(list(testler.items())):
        lift = lift_hesapla(b)
        bitti = b.get("durum") == "bitti"
        satirlar.append({
            "Test_ID": test_kodu(tid),
            "Test_Name": b.get("ad", ""),
            "Status": "Bitti" if bitti else "Aktif",
            "Brand": b.get("marka") or None,
            "Country": b.get("ulke") or None,
            "Product_Category": b.get("kategori") or None,
            "Platform": b.get("platform") or None,
            "Test_Type": b.get("test_tipi") or None,
            "Campaign_Objective": b.get("kampanya_amaci") or None,
            "Primary_Metric": b.get("metrik") or None,
            "CR_Control": sayi(b.get("kontrol_deger")),
            "CR_Treatment": sayi(b.get("varyant_deger")),
            "Lift_Percent": lift,
            "P_Value": sayi(b.get("p_degeri")),
            "Confidence": b.get("guven") or None,
            "Sample_Size": sayi(b.get("orneklem")),
            "Result": b.get("sonuc") or None,
            "Launch_Date": b.get("baslangic") or None,
            "End_Date": (b.get("bitis")
                         or ((b.get("kapanis") or "").split(" ")[0]
                             if bitti else "")) or None,
            "Added_By": b.get("ekleyen") or None,
            "Hypothesis": b.get("hipotez") or None,
            "Executive_Summary": b.get("sonuc_notu") or None,
            "Key_Learnings": b.get("insight") or None,
            "Strategic_Recommendation": b.get("sonraki_adim") or None,
            "Data_Source": "Ekip girişi"
                           + (f" ({b['ekleyen']})" if b.get("ekleyen") else ""),
            "_tid": tid,
        })
    kolonlar = ["Test_ID", "Test_Name", "Status", "Brand", "Country",
                "Product_Category", "Platform", "Test_Type",
                "Campaign_Objective", "Primary_Metric", "CR_Control",
                "CR_Treatment", "Lift_Percent", "P_Value", "Confidence",
                "Sample_Size", "Result", "Launch_Date", "End_Date", "Added_By",
                "Hypothesis", "Executive_Summary", "Key_Learnings",
                "Strategic_Recommendation", "Data_Source", "_tid"]
    return pd.DataFrame(satirlar, columns=kolonlar)


# --- Asistan metni ----------------------------------------------------------
def olcum_metni(b):
    """'CR: kontrol 0.04 → varyant 0.05 | lift +25%' gibi kisa olcum satiri."""
    parca = []
    kontrol, varyant = b.get("kontrol_deger"), b.get("varyant_deger")
    if kontrol or varyant:
        parca.append(f"{b.get('metrik') or 'metrik'}: kontrol {kontrol or '-'}"
                     f" → varyant {varyant or '-'}")
    lift = lift_hesapla(b)
    if lift is not None:
        parca.append(f"lift {lift:+.1f}% (pozitif = iyileşme)")
    for etiket, anahtar in (("p", "p_degeri"), ("güven", "guven"),
                            ("örneklem", "orneklem")):
        if b.get(anahtar):
            parca.append(f"{etiket} {b[anahtar]}")
    if b.get("sonuc"):
        parca.append("sonuç " + SONUCLAR.get(b["sonuc"], b["sonuc"])
                      .split(" ", 1)[-1])
    return " | ".join(parca)


def asistan_metni(tid, b):
    """Tek bir ekip testini asistanin okuyacagi bloga cevirir."""
    bitti = b.get("durum") == "bitti"
    satirlar = [f"- TEST [{test_kodu(tid)}]: {b.get('ad', '(isimsiz)')}"
                f" ({'bitti' if bitti else 'devam ediyor'}"
                + (f", ekleyen: {b['ekleyen']}" if b.get("ekleyen") else "")
                + ")"]
    kunye = [f"{e}: {b[a]}" for e, a in (
        ("Marka", "marka"), ("Platform", "platform"), ("Ülke", "ulke"),
        ("Kategori", "kategori"), ("Test tipi", "test_tipi"),
        ("Kampanya amacı", "kampanya_amaci")) if b.get(a)]
    if kunye:
        satirlar.append("  " + " | ".join(kunye))
    if b.get("hipotez"):
        satirlar.append(f"  Hipotez / amaç: {b['hipotez']}")
    if b.get("degiskenler"):
        satirlar.append("  Test edilen: " + " | ".join(b["degiskenler"]))
    if b.get("sabitler"):
        satirlar.append("  Sabit tutulan: " + " | ".join(b["sabitler"]))
    son = (b.get("bitis") or (b.get("kapanis") or "").split(" ")[0]
           if bitti else b.get("bitis"))
    tarih = " – ".join(x for x in (b.get("baslangic"), son) if x)
    if tarih:
        satirlar.append(f"  Tarih: {tarih}")
    olcum = olcum_metni(b)
    if olcum:
        satirlar.append(f"  {'Sonuç' if bitti else 'Ara sonuç'}: {olcum}")
    for k in kutular(b):
        parca = [x for x in (k["ad"], k["alt"], k["detay"]) if x]
        for d, e in (("deger1", "etiket1"), ("deger2", "etiket2")):
            if k[d]:
                parca.append(f"{k[e] or 'değer'} {k[d]}")
        if k["not"]:
            parca.append(k["not"])
        satirlar.append("  Karşılaştırma: " + " — ".join(parca))
    for etiket, anahtar in (("Sonuç özeti", "sonuc_notu"),
                            ("Insight / öğrenim", "insight"),
                            ("Sonraki adım", "sonraki_adim"),
                            ("Not", "not")):
        if b.get(anahtar):
            satirlar.append(f"  {etiket}: {b[anahtar]}")
    if bitti and not (b.get("sonuc_notu") or b.get("insight") or olcum):
        satirlar.append("  (Sonuç henüz girilmemiş)")
    return "\n".join(satirlar)
