"""
generate_data.py
-----------------
Gercekci ve KENDI ICINDE TUTARLI sahte dijital pazarlama verisi uretir.
"Tutarli" demek: tiklamalar gosterimden, harcama CPM'den, donusumler
tiklamadan turer -- yani metrikler birbiriyle uyumlu, uydurma degil.
Gercek musteri verisi KULLANILMAZ; her sey burada simule edilir.

Calistir:  python generate_data.py
Cikti:     data/simulated_kampanya.csv
"""

import numpy as np
import pandas as pd

rng = np.random.default_rng(seed=42)  # ayni sonucu tekrar uretmek icin sabit tohum

# --- Sabitler --------------------------------------------------------------
DATES = pd.date_range("2026-06-01", periods=14, freq="D")
PLATFORMS = ["Meta", "Google", "TikTok"]
AUDIENCES = ["18-24 Kadın", "25-34 Kadın", "25-34 Erkek", "35-44 Genel"]
CAMPAIGN = "Yaz Kampanyası - Awareness"
OBJECTIVE = "Awareness"

# Platform profilleri: (gunluk taban gosterim, CPM_TL, CTR, CVR, frekans)
# TikTok: cok gosterim/dusuk CPM | Google: yuksek niyet | Meta: ortada
# Not: awareness kampanyasi ust-huni oldugu icin CVR (donusum orani) bilerek dusuk.
PLATFORM = {
    "Meta":   dict(imp=52000, cpm=42.0, ctr=0.014, cvr=0.010, freq=2.6),
    "Google": dict(imp=38000, cpm=26.0, ctr=0.010, cvr=0.013, freq=1.6),
    "TikTok": dict(imp=90000, cpm=20.0, ctr=0.020, cvr=0.007, freq=1.9),
}

# Kitle carpanlari: bazilari yildiz, biri kasitli zayif (araç "kes" desin diye)
# (gosterim, ctr, cvr, cpm) carpanlari
AUDIENCE = {
    "18-24 Kadın": dict(imp=1.15, ctr=1.10, cvr=0.85, cpm=0.95),  # genis erisim
    "25-34 Kadın": dict(imp=1.05, ctr=1.25, cvr=1.35, cpm=1.00),  # YILDIZ segment
    "25-34 Erkek": dict(imp=0.90, ctr=0.70, cvr=0.65, cpm=1.20),  # ZAYIF segment
    "35-44 Genel": dict(imp=0.95, ctr=0.95, cvr=1.05, cpm=1.05),  # ortalama
}

AOV = 350  # ortalama sepet tutari (TL)


def noise(scale=0.12):
    """Gercekci gunluk dalgalanma icin +-%12 civari carpan."""
    return rng.normal(1.0, scale)


rows = []
for date in DATES:
    # hafta sonu tuketiciye biraz daha fazla gosterim (mevsimsellik)
    weekend = 1.15 if date.weekday() >= 5 else 1.0
    for platform in PLATFORMS:
        p = PLATFORM[platform]
        for aud in AUDIENCES:
            a = AUDIENCE[aud]

            impressions = int(p["imp"] * a["imp"] * weekend * noise())
            frequency = max(1.1, p["freq"] * noise(0.10))
            reach = int(impressions / frequency)

            ctr = p["ctr"] * a["ctr"] * noise(0.15)
            clicks = int(impressions * ctr)

            cpm = p["cpm"] * a["cpm"] * noise(0.10)
            spend = round(impressions / 1000 * cpm, 2)

            cvr = p["cvr"] * a["cvr"] * noise(0.20)
            conversions = int(clicks * cvr)

            revenue = round(conversions * AOV * noise(0.10), 2)

            rows.append({
                "date": date.strftime("%Y-%m-%d"),
                "campaign_name": CAMPAIGN,
                "ad_set": aud,
                "platform": platform,
                "objective": OBJECTIVE,
                "impressions": impressions,
                "reach": reach,
                "clicks": clicks,
                "spend": spend,
                "conversions": conversions,
                "revenue": revenue,
            })

df = pd.DataFrame(rows)
df.to_csv("data/simulated_kampanya.csv", index=False)

# Ozet -- uretilen verinin genel metrikleri (kontrol amacli)
imp, clk, spn = df.impressions.sum(), df.clicks.sum(), df.spend.sum()
cnv, rev = df.conversions.sum(), df.revenue.sum()
print(f"Satir sayisi: {len(df)}")
print(f"Toplam gosterim: {imp:,}")
print(f"CTR: {clk/imp*100:.2f}%  |  CPC: {spn/clk:.2f} TL  |  CPM: {spn/imp*1000:.2f} TL")
print(f"Donusum: {cnv:,}  |  CPA: {spn/cnv:.2f} TL  |  ROAS: {rev/spn:.2f}x")
