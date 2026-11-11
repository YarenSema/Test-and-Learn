"""
sunum.py — biten testleri sunum slaytina (PPTX) doker
-----------------------------------------------------
Her test tek slayt olur; duzen ekibin "Meta CPAS | Low-Selling Products
Test" slaytindan alinmistir:

    Baslik | alt baslik (soru + tarih)
    [Objective & Hypothesis]   TEST DESIGN — ...
     - 3 madde                  (kutu A)   VS   (kutu B)
    [01 Result] -> [02 Read]

Kurumsal logo ve arka plan icin: PowerPoint'te sablonun bos bir halini
`data/sunum_sablonu.pptx` olarak kaydet. Dosya varsa slaytlar onun
ana slaydi (logo, dalgalar) uzerine kurulur; yoksa dalgalar cizilir.
"""
import io
import math
import os

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

import ekip_testleri as et

SABLON_YOLU = os.path.join("data", "sunum_sablonu.pptx")

LACIVERT = RGBColor(0x1B, 0x27, 0x5C)
LACIVERT_2 = RGBColor(0x2E, 0x3C, 0x78)
ACIK = RGBColor(0xEE, 0xF2, 0xFB)
KENAR = RGBColor(0xC9, 0xD3, 0xEE)
LAVANTA = RGBColor(0xDD, 0xE3, 0xF5)
OK_RENGI = RGBColor(0x4A, 0x6F, 0xB5)
GRI = RGBColor(0x5B, 0x64, 0x80)
SOLUK = RGBColor(0xB9, 0xC3, 0xE6)
BEYAZ = RGBColor(0xFF, 0xFF, 0xFF)
YESIL = RGBColor(0x3D, 0xBE, 0x8B)
KIRMIZI = RGBColor(0xE0, 0x5A, 0x5A)
FONT = "Segoe UI"
SEMBOL_FONT = "Segoe UI Symbol"

ETIKETLER = {
    "en": {"amac": "OBJECTIVE & HYPOTHESIS", "tasarim": "TEST DESIGN",
           "sonuc": "Result", "okuma": "Read", "kontrol": "Control",
           "varyant": "Variant", "lift": "LIFT", "test": "Tested",
           "sabit": "Kept constant", "olcum": "Measured", "vs": "VS"},
    "tr": {"amac": "AMAÇ & HİPOTEZ", "tasarim": "TEST TASARIMI",
           "sonuc": "Sonuç", "okuma": "Çıkarım", "kontrol": "Kontrol",
           "varyant": "Varyant", "lift": "LIFT", "test": "Test edilen",
           "sabit": "Sabit tutulan", "olcum": "Ölçülen", "vs": "VS"},
}

# Koordinatlar referans slaytin ekran goruntusunden (1072 px genislik)
# olculdu; P() piksel -> EMU cevirir.
REF_GENISLIK = 1072
_olcek = Inches(13.333) / REF_GENISLIK


def P(px):
    return Emu(int(px * _olcek))


# --- Kucuk cizim yardimcilari ----------------------------------------------
def _stil_sil(sekil):
    """Temanin golge/cizgi stilini kaldir; renkler elle verilir."""
    stil = sekil._element.find(qn("p:style"))
    if stil is not None:
        sekil._element.remove(stil)


def _sekil(slayt, tur, x, y, w, h, dolgu=None, kenar=None, kenar_pt=1.0,
           yuvarlak=None, saydamlik=None):
    s = slayt.shapes.add_shape(tur, P(x), P(y), P(w), P(h))
    _stil_sil(s)
    if dolgu is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = dolgu
        if saydamlik is not None:
            _saydam(s, saydamlik)
    if kenar is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = kenar
        s.line.width = Pt(kenar_pt)
    if yuvarlak is not None and tur == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = yuvarlak
    return s


def _saydam(sekil, opaklik):
    """opaklik: 0-100 (100 = tam dolu)."""
    renk = sekil._element.spPr.find(qn("a:solidFill")).find(qn("a:srgbClr"))
    alfa = etree.SubElement(renk, qn("a:alpha"))
    alfa.set("val", str(int(opaklik * 1000)))


def _sigdir(metin, w, h, en_buyuk, en_kucuk, satir=1.22, harf=0.52):
    """
    Metni kutuya sigacak punto ile doner: (metin, punto). En kucuk puntoda
    da sigmiyorsa sonu '…' ile kisaltilir. Genislik tahmini (Segoe UI
    ortalama karakter ~0.52 em) PowerPoint'in gercek kirilimina yakin.
    """
    metin = (metin or "").strip()
    w_pt = w * _olcek / 12700
    h_pt = h * _olcek / 12700
    pt = en_buyuk
    while True:
        karakter = max(1, int(w_pt / (pt * harf)))
        satirlar = sum(max(1, math.ceil(len(p) / karakter))
                       for p in metin.split("\n"))
        if satirlar * pt * satir <= h_pt or pt <= en_kucuk:
            break
        pt -= 0.5
    sigan = max(1, int(h_pt / (pt * satir))) * karakter
    if len(metin) > sigan:
        metin = metin[:max(1, sigan - 1)].rstrip() + "…"
    return metin, pt


def _yazi(slayt, x, y, w, h, metin, pt, renk, kalin=False, italik=False,
          hiza=PP_ALIGN.LEFT, dikey=MSO_ANCHOR.TOP, font=FONT, aralik=None,
          sigdir=None, harf=0.52):
    """
    Kutuya metin yazar. metin str ya da [(parca, kalin_mi), ...] olabilir.
    sigdir=(en_kucuk_pt) verilirse punto kutuya gore kucultulur.
    """
    if isinstance(metin, str):
        parcalar = [(metin, kalin)]
    else:
        parcalar = metin
    if sigdir:
        duz = "".join(p for p, _ in parcalar)
        kisa, pt = _sigdir(duz, w, h, pt, sigdir, harf=harf)
        if kisa != duz:                       # kisaldi: tek parca yaz
            parcalar = [(kisa, kalin)]
    kutu = slayt.shapes.add_textbox(P(x), P(y), P(w), P(h))
    tf = kutu.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = dikey
    p = tf.paragraphs[0]
    p.alignment = hiza
    for parca, koyu in parcalar:
        r = p.add_run()
        r.text = parca
        r.font.name = font
        r.font.size = Pt(pt)
        r.font.bold = koyu
        r.font.italic = italik
        r.font.color.rgb = renk
        if aralik is not None:            # harf araligi (yuzde punto)
            r.font._element.set("spc", str(int(aralik * 100)))
    return kutu


def _ikon(slayt, cx, cy, cap, dolgu, sembol, renk, kare=False, pt=None,
          kenar=None):
    tur = MSO_SHAPE.ROUNDED_RECTANGLE if kare else MSO_SHAPE.OVAL
    s = _sekil(slayt, tur, cx - cap / 2, cy - cap / 2, cap, cap, dolgu=dolgu,
               kenar=kenar, kenar_pt=1.5, yuvarlak=0.22 if kare else None)
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = sembol
    r.font.name = SEMBOL_FONT
    r.font.size = Pt(pt or cap * 0.36)
    r.font.bold = True
    r.font.color.rgb = renk
    return s


def _ok(slayt, x1, y1, x2, y2, renk=OK_RENGI, pt=2.25):
    c = slayt.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, P(x1), P(y1),
                                   P(x2), P(y2))
    c.line.color.rgb = renk
    c.line.width = Pt(pt)
    ln = c.line._get_or_add_ln()
    uc = etree.SubElement(ln, qn("a:tailEnd"))
    uc.set("type", "triangle")
    uc.set("w", "med")
    uc.set("len", "med")
    return c


def _dalga(slayt, noktalar, renk, opaklik):
    """Kapali egri sekil (dekoratif dalga)."""
    bas = noktalar[0]
    fb = slayt.shapes.build_freeform(P(bas[0]), P(bas[1]), scale=1.0)
    fb.add_line_segments([(P(x), P(y)) for x, y in noktalar[1:]], close=True)
    s = fb.convert_to_shape()
    _stil_sil(s)
    s.fill.solid()
    s.fill.fore_color.rgb = renk
    _saydam(s, opaklik)
    s.line.fill.background()
    return s


def _egri(p0, p1, p2, adim=24):
    """Ikinci derece Bezier egrisi uzerindeki noktalar."""
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1])
            for t in (i / adim for i in range(adim + 1))]


def _dalgalar(slayt, genislik, yukseklik):
    """Referans slayttaki mavi kose dalgalari (sablon dosyasi yoksa)."""
    W, H = genislik, yukseklik
    acik = RGBColor(0xA9, 0xD1, 0xF7)
    orta = RGBColor(0x5A, 0xA5, 0xEE)
    koyu = RGBColor(0x2F, 0x7F, 0xE0)
    # sag ust
    _dalga(slayt, _egri((W * 0.42, 0), (W * 0.80, 0.16 * H), (W, 0.30 * H))
           + [(W, 0)], acik, 45)
    _dalga(slayt, _egri((W * 0.58, 0), (W * 0.86, 0.10 * H), (W, 0.20 * H))
           + [(W, 0)], orta, 40)
    _dalga(slayt, _egri((W * 0.74, 0), (W * 0.92, 0.05 * H), (W, 0.11 * H))
           + [(W, 0)], koyu, 45)
    # sol alt
    _dalga(slayt, _egri((0, H * 0.86), (W * 0.14, H * 0.93), (W * 0.36, H))
           + [(0, H)], acik, 45)
    _dalga(slayt, _egri((0, H * 0.92), (W * 0.10, H * 0.97), (W * 0.22, H))
           + [(0, H)], orta, 45)


# --- Testten slayt verisi ---------------------------------------------------
def _kurulum_maddeleri(b, et_):
    """Objective kutusundaki 3 madde: [(kalin_kisim, devam), ...]."""
    maddeler = []
    for satir in (b.get("kurulum") or [])[:3]:
        if ":" in satir:
            bas, son = satir.split(":", 1)
            maddeler.append((bas.strip(), " " + son.strip()))
        else:
            kelime, _, son = satir.partition(" ")
            maddeler.append((kelime, " " + son if son else ""))
    if maddeler:
        return maddeler
    if b.get("degiskenler"):
        maddeler.append((et_["test"] + ":", " " + "; ".join(b["degiskenler"])))
    if b.get("sabitler"):
        maddeler.append((et_["sabit"] + ":", " " + ", ".join(b["sabitler"])))
    if b.get("metrik"):
        maddeler.append((et_["olcum"] + ":", " " + b["metrik"]))
    if not maddeler and b.get("hipotez"):
        maddeler.append(("", b["hipotez"]))
    return maddeler[:3]


def _varsayilan_kutular(b, et_):
    """Sunum kutusu girilmemisse kontrol / varyant degerlerinden kurulur."""
    metrik = (b.get("metrik") or "").upper()
    lift = et.lift_hesapla(b)
    return [
        {"ad": et_["kontrol"], "alt": "", "detay": ", ".join(b.get("sabitler") or []),
         "deger1": b.get("kontrol_deger") or "", "etiket1": metrik,
         "deger2": "", "etiket2": "", "not": ""},
        {"ad": et_["varyant"], "alt": "",
         "detay": "; ".join(b.get("degiskenler") or []),
         "deger1": b.get("varyant_deger") or "", "etiket1": metrik,
         "deger2": f"{lift:+.1f}%" if lift is not None else "",
         "etiket2": et_["lift"] if lift is not None else "",
         "not": " · ".join(x for x in (
             f"p={b['p_degeri']}" if b.get("p_degeri") else "",
             b.get("guven") or "",
             f"n={b['orneklem']}" if b.get("orneklem") else "") if x)},
    ]


SONUC_KELIMESI = {
    "en": {"WIN": "Winner", "LOSS": "Did not win",
           "INCONCLUSIVE": "No significant difference"},
    "tr": {"WIN": "Kazandı", "LOSS": "Kazanmadı",
           "INCONCLUSIVE": "Anlamlı fark yok"},
}


def _otomatik_sonuc(b, dil):
    """Sonuc ozeti yazilmamissa sayilardan kisa bir cumle kurar."""
    et_ = ETIKETLER[dil]
    parca = []
    kontrol, varyant = b.get("kontrol_deger"), b.get("varyant_deger")
    if kontrol or varyant:
        cumle = (f"{b.get('metrik') or ''}: {et_['kontrol']} {kontrol or '–'}"
                 f" → {et_['varyant']} {varyant or '–'}").strip(": ")
        lift = et.lift_hesapla(b)
        if lift is not None:
            cumle += f" ({lift:+.1f}%)"
        parca.append(cumle)
    istatistik = ", ".join(x for x in (
        f"p={b['p_degeri']}" if b.get("p_degeri") else "",
        b.get("guven") or "",
        f"n={b['orneklem']}" if b.get("orneklem") else "") if x)
    if istatistik:
        parca.append(istatistik)
    if b.get("sonuc") in SONUC_KELIMESI[dil]:
        parca.append(SONUC_KELIMESI[dil][b["sonuc"]])
    return ". ".join(parca) or "–"


def slayt_verisi(b, dil="en"):
    """Bir testin slayttaki tum metinleri (bos alanlar varsayilanla dolar)."""
    et_ = ETIKETLER[dil]
    baslik = b.get("ad") or "Test"
    if b.get("platform") and b["platform"].lower() not in baslik.lower():
        baslik = f"{b['platform']} | {baslik}"
    bitis = b.get("bitis") or b.get("kapanis", "").split(" ")[0]
    tarih = "–".join(x for x in (b.get("baslangic"), bitis) if x)
    soru = b.get("sunum_sorusu") or b.get("hipotez") or ""
    alt = f"{soru} ({tarih})" if tarih else soru
    tasarim = (b.get("tasarim_basligi") or "").strip()
    kutu = et.kutular(b)
    if len(kutu) < 2:
        varsayilan = _varsayilan_kutular(b, et_)
        kutu = (kutu + varsayilan[len(kutu):])[:2]
    return {
        "baslik": baslik,
        "alt": alt,
        "maddeler": _kurulum_maddeleri(b, et_),
        "tasarim": et_["tasarim"] + (f" — {tasarim.upper()}" if tasarim else ""),
        "tasarim_notu": (b.get("tasarim_notu")
                         or (b.get("degiskenler") or [""])[0]),
        "kutular": kutu,
        "sonuc": b.get("sonuc_notu") or _otomatik_sonuc(b, dil),
        "okuma": b.get("insight") or "",
        "durum": b.get("sonuc", ""),
        "et": et_,
    }


# --- Slayt cizimi -----------------------------------------------------------
def _kutu_ciz(slayt, x, y, v, koyu):
    w, h = 282, 221
    _sekil(slayt, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h,
           dolgu=LACIVERT if koyu else ACIK,
           kenar=None if koyu else KENAR, yuvarlak=0.07)
    yazi = BEYAZ if koyu else LACIVERT
    soluk = SOLUK if koyu else GRI
    _ikon(slayt, x + 38, y + 38, 40, YESIL if koyu else LAVANTA, "▤",
          BEYAZ if koyu else LACIVERT, pt=15)
    _yazi(slayt, x + 68, y + 18, w - 82, 22, v["ad"].upper(), 13, yazi,
          kalin=True, sigdir=9)
    if v["alt"]:
        _yazi(slayt, x + 68, y + 40, w - 82, 18, v["alt"], 10, soluk,
              italik=True, sigdir=8)
    if v["detay"]:
        _yazi(slayt, x + 18, y + 72, w - 36, 40, v["detay"], 11, yazi,
              sigdir=8)
    for i, (d, e) in enumerate((("deger1", "etiket1"), ("deger2", "etiket2"))):
        if not v[d]:
            continue
        sx = x + 18 + i * 124
        _yazi(slayt, sx, y + 116, 118, 44, v[d], 28, yazi, kalin=True,
              sigdir=14, dikey=MSO_ANCHOR.BOTTOM)
        if v[e]:
            _yazi(slayt, sx, y + 162, 118, 16, v[e].upper(), 8.5, soluk,
                  kalin=True, sigdir=6.5, aralik=0.5)
    if v["not"]:
        _yazi(slayt, x + 18, y + 186, w - 36, 28, v["not"], 9.5, soluk,
              italik=True, sigdir=7.5)


def _slayt_ciz(slayt, v, dalga, genislik_px, yukseklik_px):
    et_ = v["et"]
    if dalga:
        _dalgalar(slayt, genislik_px, yukseklik_px)

    _yazi(slayt, 27, 20, 880, 46, v["baslik"], 28, LACIVERT, kalin=True,
          sigdir=18, dikey=MSO_ANCHOR.MIDDLE)
    _yazi(slayt, 27, 72, 900, 34, v["alt"], 11, GRI, italik=True, sigdir=8.5)

    # Sol: amac & hipotez
    _sekil(slayt, MSO_SHAPE.ROUNDED_RECTANGLE, 47, 118, 326, 320,
           dolgu=LACIVERT, yuvarlak=0.06)
    _ikon(slayt, 86, 160, 34, None, "◎", BEYAZ, pt=20)
    _yazi(slayt, 112, 146, 250, 28, et_["amac"], 13.5, BEYAZ, kalin=True,
          dikey=MSO_ANCHOR.MIDDLE, aralik=0.5, sigdir=10)
    semboller = ("▦", "◉", "✦")
    for i, (kalin, devam) in enumerate(v["maddeler"]):
        cy = 228 + i * 84
        _ikon(slayt, 90, cy, 38, LACIVERT_2, semboller[i], BEYAZ, kare=True,
              pt=15)
        metin, pt = _sigdir(kalin + devam, 238, 70, 11.5, 8)
        if metin != kalin + devam:
            parcalar = [(metin, False)]
        else:
            parcalar = [(kalin, True), (devam, False)]
        _yazi(slayt, 122, cy - 34, 238, 70, parcalar, pt, BEYAZ,
              dikey=MSO_ANCHOR.MIDDLE)

    # Sag: test tasarimi
    # Buyuk harf + harf araligi: karakter basina genislik daha fazla
    _yazi(slayt, 398, 128, 272, 24, v["tasarim"], 13, LACIVERT, kalin=True,
          aralik=1.0, sigdir=8, harf=0.68, dikey=MSO_ANCHOR.MIDDLE)
    _ikon(slayt, 712, 160, 54, LAVANTA, "⚇", LACIVERT, pt=20)
    if v["tasarim_notu"]:
        _yazi(slayt, 748, 140, 280, 40, v["tasarim_notu"], 11, LACIVERT,
              italik=True, sigdir=8.5, dikey=MSO_ANCHOR.MIDDLE)
    _ok(slayt, 690, 182, 610, 216)
    _ok(slayt, 734, 182, 814, 216)

    _kutu_ciz(slayt, 398, 217, v["kutular"][0], koyu=False)
    _kutu_ciz(slayt, 743, 217, v["kutular"][1], koyu=True)
    _ikon(slayt, 711, 357, 54, LACIVERT, et_["vs"], BEYAZ, pt=14,
          kenar=BEYAZ)

    # Alt: 01 Result -> 02 Read
    _sekil(slayt, MSO_SHAPE.ROUNDED_RECTANGLE, 47, 460, 978, 112,
           dolgu=ACIK, kenar=KENAR, yuvarlak=0.12)
    durum_rengi = {"WIN": YESIL, "LOSS": KIRMIZI}.get(v["durum"], LACIVERT)
    adimlar = [("01", 98, et_["sonuc"], v["sonuc"], 208),
               ("02", 433, et_["okuma"], v["okuma"], 560)]
    if not v["okuma"]:                  # insight yok: sonuc tum genisligi alsin
        adimlar = [("01", 98, et_["sonuc"], v["sonuc"], 870)]
    for no, cx, baslik, metin, gen in adimlar:
        _ikon(slayt, cx, 516, 46, LAVANTA, "↗" if no == "01" else "⌕",
              LACIVERT, pt=17)
        _ikon(slayt, cx + 16, 491, 22, durum_rengi if no == "01" else LACIVERT,
              no, BEYAZ, pt=8)
        _yazi(slayt, cx + 37, 480, gen, 22, baslik, 13, LACIVERT, kalin=True)
        _yazi(slayt, cx + 37, 503, gen, 62, metin, 10.5, LACIVERT, sigdir=8)
    if len(adimlar) == 2:
        _yazi(slayt, 352, 497, 40, 36, "→", 26, OK_RENGI, kalin=True,
              font=SEMBOL_FONT, hiza=PP_ALIGN.CENTER)


def _sunum_hazirla():
    """Sablon dosyasi varsa onu (slaytlari silinmis), yoksa bos 16:9 sunum."""
    if os.path.exists(SABLON_YOLU):
        try:
            prs = Presentation(SABLON_YOLU)
            liste = prs.slides._sldIdLst
            for sid in list(liste):
                prs.part.drop_rel(sid.rId)
                liste.remove(sid)
            duzen = min(prs.slide_layouts, key=lambda d: len(d.placeholders))
            return prs, duzen, False
        except Exception:
            pass                      # bozuk sablon: varsayilan cizime don
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs, prs.slide_layouts[6], True


def sunum_olustur(testler, dil="en"):
    """testler: [bilgi, ...] -> PPTX dosyasinin byte'lari."""
    global _olcek
    prs, duzen, dalga = _sunum_hazirla()
    _olcek = prs.slide_width / REF_GENISLIK
    yukseklik_px = prs.slide_height / _olcek
    for b in testler:
        slayt = prs.slides.add_slide(duzen)
        for yer in list(slayt.placeholders):          # bos "baslik ekle" kutulari
            yer._element.getparent().remove(yer._element)
        _slayt_ciz(slayt, slayt_verisi(b, dil), dalga, REF_GENISLIK,
                   yukseklik_px)
    tampon = io.BytesIO()
    prs.save(tampon)
    return tampon.getvalue()
