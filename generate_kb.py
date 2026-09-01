"""
generate_kb.py
---------------
Asistanin "gecmis test hafizasi" olacak simule Test & Learn bilgi tabanini uretir.
Her satir: gecmiste yapilmis bir test/kampanya, ne test edildi, sonucu ne oldu,
ne ogrenildi. Asistan yeni sorulara cevap verirken bu ogrenimlere dayanir.

Gercek sirket verisi DEGILDIR; hepsi temsili/simuledir.
Calistir:  python generate_kb.py   ->  data/test_learn_kb.csv

Yeni bir ogrenim eklemek istersen: asagidaki listeye yeni bir satir ekle,
ya da uretilen CSV'yi Excel'de acip yeni satir yaz. Ikisi de calisir.
"""

import pandas as pd

# (donem, urun, amac, platform, hedef_kitle, test_edilen_degisken, kazanan, etki, ogrenim)
DENEYLER = [
    ("2025-Q1", "Cilt Bakım Serumu", "Awareness", "TikTok", "18-24 Kadın",
     "UGC içerik vs stüdyo çekimi", "UGC", "CTR +42%",
     "TikTok'ta doğal/UGC içerik stüdyo çekimini geçiyor, özellikle genç kitlede."),
    ("2025-Q1", "Vitamin Takviyesi", "Awareness", "TikTok", "18-24 Genel",
     "6 sn video vs 15 sn video", "6 sn", "CPV -31%",
     "Awareness'ta ilk 3 sn'de güçlü hook + kısa video erişim verimliliğini artırıyor."),
    ("2025-Q1", "Ağız Bakım", "Conversion", "Meta", "Geniş (Advantage+)",
     "Geniş kitle vs dar manuel kitle", "Geniş", "CPA -18%",
     "Meta'da geniş/Advantage+ kitle çoğu zaman dar manuel kitleyi geçiyor; algoritmaya alan tanı."),
    ("2025-Q2", "Cilt Bakım Serumu", "Conversion", "Meta", "%1 Lookalike",
     "Lookalike vs ilgi bazlı soğuk kitle", "Lookalike", "ROAS +0.6x",
     "Mevcut müşteri lookalike'ı, soğuk ilgi kitlesinden daha verimli dönüşüm getiriyor."),
    ("2025-Q2", "Ev Bakım", "Awareness", "Meta", "25-44 Kadın",
     "Statik görsel vs video", "Video", "CPM -22%",
     "Awareness'ta video daha ucuz erişim sağlıyor; ancak conversion'da statik carousel bazen daha iyi."),
    ("2025-Q2", "Vitamin Takviyesi", "Conversion", "Meta", "25-44 Genel",
     "'%20 indirim' vs '100 TL kazan' mesajı", "Duruma göre", "CVR ±",
     "İndirim çerçevesi ürün fiyatına bağlı: düşük fiyatta yüzde, yüksek sepette TL tutarı daha iyi çalışıyor."),
    ("2025-Q2", "Saç Bakım", "Conversion", "Meta", "Retargeting",
     "Frekans limiti 3 vs 7", "3", "CPA -15%",
     "Yüksek frekans dönüşüm getirmiyor; sadece maliyeti ve reklam yorgunluğunu artırıyor."),
    ("2025-Q3", "Güneş Koruyucu", "Awareness", "TikTok", "18-34 Genel",
     "TikTok vs Meta (aynı awareness kampanyası)", "TikTok", "CPM -35%",
     "Genç kitlede awareness için TikTok daha ucuz erişim; 35+ yaş için Meta daha güçlü."),
    ("2025-Q3", "Ağız Bakım", "Conversion", "Google", "Arama",
     "Marka araması vs marka dışı araması", "Ayrı bütçe", "—",
     "Marka aramada CPC düşük/yüksek dönüşüm ama ölçek sınırlı; marka dışı ölçek verir ama pahalı. İkisini ayrı bütçele."),
    ("2025-Q3", "Vitamin Takviyesi", "Awareness", "YouTube", "25-44 Genel",
     "6 sn bumper vs 15 sn skippable", "Bumper", "Marka hatırlanırlığı +",
     "Kısa bumper reklamlar marka hatırlanırlığında ve CPM'de verimli."),
    ("2025-Q3", "Cilt Bakım Serumu", "Conversion", "Meta", "25-34",
     "Erkek segment vs kadın segment (aynı ürün)", "Kadın", "ROAS 2.9x vs 0.5x",
     "25-34 kadın dönüşümde çok güçlü, erkek segment zayıf; erkek için mesaj ve kreatif farklılaştırılmalı."),
    ("2025-Q4", "Ev Bakım", "Conversion", "Meta", "Soğuk kitle",
     "CTA 'Hemen Al' vs 'Keşfet'", "Duruma göre", "—",
     "Conversion'da 'Hemen Al' doğrudan satışta iyi; awareness/consideration'da 'Keşfet' tıklama kalitesini artırıyor."),
    ("2025-Q4", "Saç Bakım", "Conversion", "Meta", "Mobil",
     "Sabah vs akşam yayın (dayparting)", "Akşam 20-23", "CVR +19%",
     "Akşam saatlerinde dönüşüm oranı gündüzden yüksek; bütçe ağırlığını akşama kaydır."),
    ("2025-Q4", "Cilt Bakım Serumu", "Conversion", "Meta", "Sepeti terk edenler",
     "Tek ürün reklamı vs dinamik katalog (DPA)", "Katalog", "ROAS +0.8x",
     "Sepeti terk edenlerde dinamik ürün reklamı (DPA) ROAS'ı belirgin artırıyor."),
    ("2025-Q4", "Vitamin Takviyesi", "Conversion", "Meta", "Trafik",
     "Genel ürün sayfası vs kampanyaya özel landing", "Özel landing", "CVR +27%",
     "Kampanyaya özel, sade bir landing sayfası dönüşüm oranını artırıyor."),
    ("2026-Q1", "Güneş Koruyucu", "Awareness", "TikTok", "18-24",
     "Marka hesabı vs influencer whitelisting (Spark Ads)", "Spark Ads", "CTR +33%",
     "Influencer içeriğini reklamla güçlendirmek (Spark Ads) güveni ve tıklamayı artırıyor."),
    ("2026-Q1", "Saç Bakım", "Conversion", "Meta", "Ölçekleme",
     "Kademeli %20/gün vs ani 2x bütçe artışı", "Kademeli", "CPA korundu",
     "Ani 2x bütçe artışı öğrenme fazını bozup CPA'yı yükseltiyor; kademeli ölçekle."),
    ("2026-Q1", "Vitamin Takviyesi", "Consideration", "Meta", "25-44",
     "Tek görsel vs carousel (fayda anlatımı)", "Carousel", "Etkileşim +24%",
     "Çok faydalı/eğitici ürünlerde carousel etkileşimi ve consideration'ı artırıyor."),
    ("2026-Q1", "Ev Bakım", "Awareness", "TikTok", "Genel",
     "Altyazılı vs altyazısız video", "Altyazılı", "Tamamlanma +30%",
     "Sessiz izlemede altyazılı videolar tamamlanma oranını artırıyor; her videoya altyazı ekle."),
    ("2026-Q2", "Yeni Ürün: Nem Kremi", "Karma", "Meta+TikTok", "Genel",
     "Awareness+Conversion eşzamanlı vs sıralı (önce ısıt)", "Sıralı", "Toplam CPA -21%",
     "Lansmanda 1-2 hafta awareness ile kitleyi ısıtıp sonra conversion açmak toplam CPA'yı düşürüyor."),
    ("2026-Q2", "Cilt Bakım Serumu", "Conversion", "Meta", "Test aşaması",
     "ABO vs CBO", "ABO→CBO", "—",
     "Test aşamasında ABO ile kreatif/kitle ayrıştırması net; kazananlar bulununca CBO ile ölçekle."),
    ("2026-Q2", "Premium Anti-Aging", "Consideration", "Meta", "35-54 Kadın",
     "Fiyat vurgusu vs fayda/değer vurgusu", "Fayda", "Marka algısı +",
     "Premium konumlandırmada fiyat yerine değer/fayda mesajı marka algısını koruyor."),
    ("2026-Q2", "Vitamin Takviyesi", "Conversion", "Meta", "Yaş grupları",
     "Geniş 18-45 vs bölünmüş yaş grupları", "Ölçekte geniş", "—",
     "Bölünmüş yaş gruplarıyla ayrı kreatif dönüşümü artırıyor ama yönetim maliyeti yüksek; ölçekte geniş bırak."),
    ("2026-Q2", "Güneş Koruyucu", "Karma", "Meta+Google", "Genel",
     "Sezon başı vs sezon zirvesi bütçe dağılımı", "Kaydırmalı", "Satış +",
     "Sezon başında (Mayıs) erken awareness, zirvede (Temmuz) conversion bütçesine kaydırma satışları artırıyor."),
    ("2026-Q2", "Ağız Bakım", "Conversion", "Meta", "CRM/mevcut müşteri",
     "Yeni kitle vs mevcut müşteri (upsell)", "Mevcut müşteri", "En yüksek ROAS",
     "Mevcut müşteriye upsell reklamı en yüksek ROAS'ı veren kitle; ayrı kampanya aç."),
    ("2026-Q2", "Yeni Marka: Doğal Bakım", "Conversion", "Meta", "Soğuk kitle",
     "Problem-çözüm vs sosyal kanıt (yorumlar)", "Sosyal kanıt", "CVR +22%",
     "Yeni/az bilinen markada sosyal kanıt (kullanıcı yorumu) dönüşümü artırıyor; bilinen markada problem-çözüm yeterli."),
]

COLS = ["donem", "urun", "amac", "platform", "hedef_kitle",
        "test_edilen_degisken", "kazanan", "etki", "ogrenim"]

df = pd.DataFrame(DENEYLER, columns=COLS)
df.insert(0, "deney_id", [f"T{i:03d}" for i in range(1, len(df) + 1)])
df.to_csv("data/test_learn_kb.csv", index=False)
print(f"{len(df)} deney yazildi -> data/test_learn_kb.csv")
