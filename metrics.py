"""
metrics.py
-----------
Bu dosya, kampanya verisindeki metrikleri KOD ile hesaplar.
ÖNEMLI: Metrikleri asla yapay zekaya "sen hesapla" demiyoruz.
Sayilari burada pandas ile guvenilir sekilde hesaplayip, YZ'ye
sadece YORUMLAMASI icin hazir veriyoruz. Projenin en kritik kurali bu.
"""

import pandas as pd


# --- 1) Kolon isimlerini standartlastirma ---------------------------------
# Meta, Google Ads ve TikTok ayni seyi FARKLI isimlerle export eder.
# Ornek: Meta "Impressions" der, Google "Impr." der, TikTok "impressions".
# Asagidaki sozluk, tum bu varyasyonlari tek bir standart isme cevirir.
# Yeni bir kolon ismiyle karsilasirsan buraya eklemen yeterli.
COLUMN_ALIASES = {
    "impressions": ["impressions", "impr", "impr.", "gosterim", "gösterim"],
    "reach": ["reach", "erisim", "erişim", "unique reach"],
    "clicks": ["clicks", "link clicks", "tiklama", "tıklama", "clicks (all)"],
    "spend": ["spend", "cost", "amount spent", "harcama", "maliyet", "spent"],
    "conversions": ["conversions", "results", "purchases", "donusum",
                    "dönüşüm", "conv.", "sonuc", "sonuç"],
    "revenue": ["revenue", "purchase value", "conversion value", "gelir",
                "value", "ciro"],
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Gelen tablonun kolon isimlerini standart isimlere cevirir."""
    df = df.copy()
    rename_map = {}
    for standard_name, variants in COLUMN_ALIASES.items():
        for col in df.columns:
            if str(col).strip().lower() in variants:
                rename_map[col] = standard_name
    df = df.rename(columns=rename_map)
    return df


# --- 2) Metrikleri hesaplama ----------------------------------------------
def _safe_div(a, b):
    """Sifira bolme hatasini onler."""
    return (a / b) if b else 0.0


def compute_metrics(df: pd.DataFrame) -> dict:
    """
    Standartlastirilmis tablodan toplam metrikleri hesaplar.
    Eksik kolonlar olursa o metrigi atlar, hata vermez.
    """
    df = normalize_columns(df)

    # Sayisal kolonlari toplariz (varsa)
    totals = {}
    for col in ["impressions", "reach", "clicks", "spend",
                "conversions", "revenue"]:
        if col in df.columns:
            totals[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).sum()

    imp = totals.get("impressions", 0)
    reach = totals.get("reach", 0)
    clicks = totals.get("clicks", 0)
    spend = totals.get("spend", 0)
    conv = totals.get("conversions", 0)
    rev = totals.get("revenue", 0)

    # Turetilmis metrikler (yaygin dijital pazarlama formulleri)
    metrics = {
        "Toplam Gösterim (Impressions)": imp,
        "Toplam Erişim (Reach)": reach,
        "Toplam Tıklama (Clicks)": clicks,
        "Toplam Harcama (Spend)": round(spend, 2),
        "Toplam Dönüşüm (Conversions)": conv,
        "CTR (%)": round(_safe_div(clicks, imp) * 100, 2),      # tiklama orani
        "CPC (tıklama başı maliyet)": round(_safe_div(spend, clicks), 2),
        "CPM (bin gösterim maliyeti)": round(_safe_div(spend, imp) * 1000, 2),
        "CPA (dönüşüm başı maliyet)": round(_safe_div(spend, conv), 2),
        "Dönüşüm Oranı (%)": round(_safe_div(conv, clicks) * 100, 2),
        "Frekans (Impr/Reach)": round(_safe_div(imp, reach), 2),
    }
    if rev:
        metrics["ROAS (getiri/harcama)"] = round(_safe_div(rev, spend), 2)

    return metrics


def metrics_to_text(metrics: dict) -> str:
    """Metrik sozlugunu, YZ'ye baglam olarak verecegimiz duz metne cevirir."""
    return "\n".join(f"- {k}: {v}" for k, v in metrics.items())
