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

## Ekip kullanımı: ortak sohbetler, ortak dosyalar, aktif testler
Uygulamaya giren herkes **aynı** sohbetleri, dosyaları ve aktif testleri
görür — biri bir soru sorduğunda diğerleri o sohbeti açıp öğrenebilir.
Girişte istenen **ad**, açtığın sohbetin ve yüklediğin dosyanın yanında görünür.

- **Sohbetler:** Sol menüde herkesin sohbeti listelenir (`Ad · başlık`).
  Yanındaki 🗄️ ile sohbet **arşive** taşınır (silinmez). Arşivden
  **↩️ Geri al** ile geri gelir; gerçekten silmek istersen arşiv ekranında
  **🗑️ Kalıcı sil** vardır (onay sorar).
- **Ortak dosyalar:** Kim yüklerse yüklesin herkes görür; listede
  "yükleyen" bilgisi yazar.
- **🟢 Aktif testler:** Devam eden testler (hipotez, değişkenler, sabitler)
  herkese açıktır; test bitince **✅ Testi bitir** ile kapatılır.

### Kalıcı depolama (Supabase) — cihazdan bağımsız, silinmeyen kayıt
Streamlit Cloud'un diski **geçicidir**: uygulama uyuyup uyandığında veya yeni
sürüm yayınlandığında `chats.json` ve `files/` silinir. Kalıcı olması için
Supabase (ücretsiz) bağlanır:

1. https://supabase.com → ücretsiz hesap → **New project** (bölge: Frankfurt).
2. Sol menü → **SQL Editor** → `supabase_kurulum.sql` dosyasının tamamını
   yapıştır → **Run**. (Tabloları ve dosya deposunu kurar.)
3. **Project Settings → API**: `Project URL` ve `anon` anahtarını kopyala.
4. Streamlit Cloud → **Manage app → Settings → Secrets** içine ekle:

       gemini_api_key = "AIza..."
       supabase_url   = "https://xxxx.supabase.co"
       supabase_key   = "eyJhbGciOi..."

   (Lokalde `.env` dosyasına `SUPABASE_URL=` / `SUPABASE_KEY=` yazılır.)
5. Sol menüdeki **Ayarlar** bölümünde "✅ Bulut depolama açık" yazmalı.

Bağlantı tek bir yerden kurulur: `depo.py` içindeki **`supabase_client()`**
(resmi `supabase` paketi, `@st.cache_resource` ile önbelleklenir; önce
`st.secrets`, yoksa `.env` okunur). Paket `requirements.txt` içinde — lokalde
`pip install -r requirements.txt`, Streamlit Cloud'da otomatik kurulur.
Buluta ulaşılamazsa uygulama çökmez: ekranda `st.warning` ile uyarır, kayıtları
geçici olarak yerel dosyaya yazar ve 60 saniye boyunca tekrar denemez.

**Eski sohbetlerini taşımak için** (kendi bilgisayarında, bir kez):

    python aktar_supabase.py

`chats.json`, yüklediğin dosyalar ve aktif testler buluta kopyalanır; script
tekrar çalıştırılsa bile kayıtlar çoğalmaz.

> Supabase ayarlanmazsa uygulama eskisi gibi çalışır, sadece veriler sunucu
> yeniden başlayınca silinir (sol menüde turuncu uyarı olarak görünür).

## Notlar
- Terminali kapatma; uygulama çalıştığı sürece açık kalmalı.
- Gerçek şirket verisini KOYMA; sadece sahte veriyle test et (onay sürecine kadar).
- Farklı senaryolar üretmek için: python generate_data.py
