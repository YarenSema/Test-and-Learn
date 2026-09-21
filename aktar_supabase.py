"""
aktar_supabase.py — eski yerel verileri buluta tasir (tek seferlik)
-------------------------------------------------------------------
Kendi bilgisayarindaki chats.json, files/ ve aktif test kayitlarini
Supabase'e yukler. Boylece Supabase'e gecince eski sohbetlerin kaybolmaz.

CALISTIRMA (proje klasorunde, terminalde):
    python aktar_supabase.py

Oncesinde .env dosyasina sunlari eklemis olmalisin:
    SUPABASE_URL=https://xxxx.supabase.co
    SUPABASE_KEY=eyJhbGciOi...

Notlar:
  - Ayni id'li kayit bulutta varsa uzerine yazilir; script'i birden fazla
    kez calistirmak veriyi cogaltmaz.
  - Hicbir yerel dosya silinmez; sadece kopyalanir.
"""
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

if not (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY")):
    print("HATA: .env dosyasinda SUPABASE_URL ve SUPABASE_KEY yok.")
    print("Kurulum adimlari icin supabase_kurulum.sql dosyasinin basina bak.")
    sys.exit(1)

import depo   # noqa: E402  (ayarlar yuklendikten sonra import edilmeli)

if not depo.bulut_acik():
    print("HATA: Supabase baglantisi kurulamadi (URL/anahtar hatali olabilir).")
    sys.exit(1)


def _oku(yol):
    try:
        with open(yol, "r", encoding="utf-8") as f:
            veri = json.load(f)
        return veri if isinstance(veri, dict) else {}
    except Exception:
        return {}


def sohbetleri_aktar(varsayilan_yazar):
    sohbetler = _oku(depo.CHATS_FILE)
    if not sohbetler:
        print("• Sohbet bulunamadi (chats.json yok ya da bos).")
        return 0
    sayac = 0
    for cid, sohbet in sohbetler.items():
        sohbet = dict(sohbet)
        sohbet.setdefault("title", "Yeni sohbet")
        sohbet.setdefault("messages", [])
        sohbet.setdefault("arsiv", False)
        if not sohbet.get("yazar"):
            sohbet["yazar"] = varsayilan_yazar
        depo.sohbet_kaydet(cid, sohbet)
        sayac += 1
        print(f"  ✓ {sohbet['title'][:45]} ({len(sohbet['messages'])} mesaj)")
    return sayac


def dosyalari_aktar(varsayilan_yazar):
    meta = _oku(depo.FILES_META)
    if not meta:
        print("• Yuklenmis dosya kaydi yok.")
        return 0
    sayac = 0
    for fid, bilgi in meta.items():
        yol = os.path.join(depo.FILES_DIR, bilgi.get("disk_adi", ""))
        if not os.path.exists(yol):
            print(f"  ! {bilgi.get('ad')} diskte bulunamadi, atlandi.")
            continue
        with open(yol, "rb") as f:
            icerik = f.read()
        depo.dosya_kaydet(icerik, bilgi.get("ad", "dosya"),
                          kategori=bilgi.get("kategori", "Rapor / diğer"),
                          notu=bilgi.get("not", ""),
                          yukleyen=bilgi.get("yukleyen") or varsayilan_yazar,
                          fid=fid)   # ayni kimlik: tekrar calisirsa cogalmaz
        sayac += 1
        print(f"  ✓ {bilgi.get('ad')} ({round(len(icerik) / 1024, 1)} KB)")
    return sayac


def testleri_aktar(varsayilan_yazar):
    testler = _oku(depo.AKTIF_TESTLER_FILE)
    if not testler:
        print("• Aktif test kaydi yok.")
        return 0
    for tid, bilgi in testler.items():
        bilgi = dict(bilgi)
        bilgi.setdefault("ekleyen", varsayilan_yazar)
        depo.test_kaydet(tid, bilgi)
        print(f"  ✓ {bilgi.get('ad', '(isimsiz test)')} "
              f"[{bilgi.get('durum', 'aktif')}]")
    return len(testler)


if __name__ == "__main__":
    yazar = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not yazar:
        yazar = input("Eski kayitlar kimin adina yazilsin? (orn: Yaren): ").strip()
    yazar = yazar or "Arşiv"

    print("\n=== SOHBETLER ===")
    s = sohbetleri_aktar(yazar)
    print("\n=== DOSYALAR ===")
    d = dosyalari_aktar(yazar)
    print("\n=== AKTİF TESTLER ===")
    t = testleri_aktar(yazar)

    print(f"\nBitti: {s} sohbet, {d} dosya, {t} test buluta aktarildi.")
    print("Uygulamayi acip sol menuden kontrol edebilirsin.")
