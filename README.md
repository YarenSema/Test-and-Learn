# Dijital Pazarlama Copilot — Kurulum (Kişisel Windows Bilgisayarı)

Kampanya verini yükleyip metriklerini gören ve yapay zeka (ücretsiz Gemini)
ile sohbet ederek test/optimizasyon önerisi alabildiğin bir araç.
İçinde hazır sahte veri (`data/simulated_kampanya.csv`) ile gelir.

## 1) İndir (bir kez)
1. Python 3.10+ → https://www.python.org/downloads  (kurarken "Add Python to PATH" işaretle)
2. VS Code → https://code.visualstudio.com  (içine "Python" eklentisini kur)

## 2) Klasörü aç
Bu klasörü (`dijital-copilot`) VS Code'da **File → Open Folder** ile aç.
Sol panelde app.py, metrics.py, data görünmeli.

## 3) API anahtarını gir
1. https://aistudio.google.com/apikey → ücretsiz "Create API key" (kredi kartı gerekmez).
2. VS Code'da yeni dosya oluştur, adını `.env` koy (baştaki nokta dahil).
3. İçine şunu yaz, `...` yerine anahtarını yapıştır, Ctrl+S ile kaydet:
   GOOGLE_API_KEY=...

## 4) Paketleri kur ve çalıştır
VS Code'da **Terminal → New Terminal**, sonra:

    pip install -r requirements.txt
    python -m streamlit run app.py

Tarayıcıda otomatik açılır (http://localhost:8501). Kişisel bilgisayarda
güvenlik duvarı engeli olmadığı için arayüz düzgün görünür.

## 5) Dene
Yükleme kutusuna `data/simulated_kampanya.csv` dosyasını seç → metrikleri gör →
sohbete yaz: "Awareness'ı artırmak için hangi testleri önerirsin?"

## Test & Learn havuzları (banyo kategorisi + gerçek kampanyalar)
`data/` klasöründeki üç dosya uygulamaya gömülüdür ve sol panelden
**🛁 Banyo kategorisi & test havuzları → 🧪 Test havuzları** ile açılır.
Her dosya kendi **sekmesinde** durur:

| Sekme | Dosya | İçerik |
|---|---|---|
| 🛁 Banyo kategorisi (35) | `Bathroom_Category_Test_Learn_MEGA.xlsx` | Vitra, Artema, İntema, Grohe, Hansgrohe, Duravit, Kohler e-ticaret testleri (PDP, Checkout, Email, Cart, Category) |
| 📚 Master veritabanı (58) | `Test_Learn_Database_MASTER_58_Tests_COMPLETE.csv` | Yukarıdakiler + Meta/Google platform testleri + **15 gerçek Eczacıbaşı Meta kampanyası (REAL###)**; **10 kaybeden (LOSS) test** dahil |
| ✨ Zenginleştirilmiş (43) | `Test_Learn_Database_ENRICHED_43_Tests.csv` | Yönetici özeti, stratejik tavsiye, beklenen getiri, uygulama zorluğu, benzer testler |

**Bu dosyalar iç içe geçmiştir:** Banyo 35 ⊂ Zenginleştirilmiş 43 ⊂ Master 58.
Ekranda hepsi ayrı ayrı görünür ama asistanın hafızasına `Test_ID`'ye göre
**tekilleştirilmiş 58 test** gider — aynı deney modele üç kez verilmez.
Dosyaların birinde olup diğerinde olmayan kolonlar (örn. `Expected_ROI`)
birleştirilir.

- Her sekmede markaya, ülkeye, ürün kategorisine, test tipine, kampanya
  amacına, **sonuca (WIN/LOSS)** ve minimum lift'e göre filtreleyebilirsin.
- Her testin altında öğrenim, iş etkisi, yönetici özeti, stratejik tavsiye,
  uygulama planı, dikkat edilecekler ve beklenen getiri yazar. 🔴 işareti
  kaybeden testi gösterir.
- **💬 Bu testleri sohbette kullan** ile filtrelediğin testleri bir sonraki
  sorunun bağlamına ekle.
- Sol paneldeki **Asistanın hafızası** seçimi:
  `Özet` (önerilen, ~30k token) · `Tam` (yönetici özeti + uygulama planı da
  eklenir, yanıtlar yavaşlar) · `Kapalı`.
- Dosyaları güncellersen (aynı isimle üzerine yazarsan) uygulama yeni hâlini
  otomatik okur; kolon isimlerini (`Test_ID`, `Lift_Percent`, ...) koru.
  Yeni bir dosya eklemek için `test_havuzu.py` içindeki `VERI_KUMELERI`
  sözlüğüne bir satır eklemen yeterli — sekmesi kendiliğinden açılır.
- Havuzdaki testlerin bir kısmı sektör benchmark'ı / mock, `REAL###` kodlular
  ise gerçek kampanya verisidir; asistan öneri verirken `Data_Source`
  kolonuna göre bunu belirtir ve kaybeden testleri "bunu yapmayın" uyarısı
  olarak kullanır.

## Notlar
- Terminali kapatma; uygulama çalıştığı sürece açık kalmalı.
- Gerçek şirket verisini KOYMA; sadece sahte veriyle test et (onay sürecine kadar).
- Farklı senaryolar üretmek için: python generate_data.py
