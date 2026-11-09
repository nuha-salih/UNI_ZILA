"""
pdf_report.py — تصدير التقرير إلى PDF (ReportLab + خط DejaVu Sans المضمَّن + تشكيل عربي داخلي).

التخطيط من اليمين لليسار: كل سطر يُرسم محاذياً لليمين بعد تحويله إلى ترتيب بصري.
الهوية: الشعار الرسمي كما هو على خلفية بيضاء أعلى اليمين، شريط عنوان أزرق داكن وخط ذهبي.
"""
from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from .arabic_text import shape, visual, wrap
from .report_data import Report

ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = ROOT / "assets" / "fonts"
LOGO = ROOT / "brand" / "nu_logo.png"
NAVY, GOLD, GREEN, INK, MUTED = (HexColor("#1C3D6A"), HexColor("#CC9E0A"), HexColor("#009673"),
                                  HexColor("#1F2933"), HexColor("#4A5568"))
ROW_ALT = HexColor("#F3F6FA")
PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
_FONTS_READY = False


def _fonts():
    global _FONTS_READY
    if not _FONTS_READY:
        pdfmetrics.registerFont(TTFont("NU-Regular", str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("NU-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
        _FONTS_READY = True


class _Writer:
    def __init__(self, rep: Report):
        _fonts()
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=A4)
        self.c.setTitle(rep.title)
        self.c.setAuthor("ZILAL AI prototype")
        self.rep = rep
        self.page = 0
        self.right = PAGE_W - MARGIN
        self.left = MARGIN
        self.new_page()

    # ---- primitives -------------------------------------------------------
    def width(self, s, font="NU-Regular", size=10):
        return pdfmetrics.stringWidth(s, font, size)

    def text_r(self, s, x, y, font="NU-Regular", size=10, color=INK):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        self.c.drawRightString(x, y, visual(str(s)))

    def text_l(self, s, x, y, font="NU-Regular", size=10, color=INK):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        self.c.drawString(x, y, visual(str(s)))

    def ensure(self, h):
        if self.y - h < MARGIN + 14 * mm:
            self.new_page()

    def new_page(self):
        if self.page:
            self.c.showPage()
        self.page += 1
        c = self.c
        top = PAGE_H - MARGIN
        if LOGO.exists():
            img = ImageReader(str(LOGO))
            iw, ih = img.getSize()
            w = 34 * mm
            h = w * ih / iw
            c.drawImage(img, self.right - w, top - h, width=w, height=h, mask="auto")
            head_h = h
        else:
            head_h = 20 * mm
        self.text_l("مدعوم بتقنية ظِلال AI", self.left, top - 6 * mm, size=8, color=MUTED)
        self.text_l("نموذج أولي تجريبي — بيانات محاكاة", self.left, top - 11 * mm, size=8, color=MUTED)
        y = top - head_h - 4 * mm
        c.setFillColor(NAVY)
        c.rect(self.left, y - 11 * mm, self.right - self.left, 11 * mm, fill=1, stroke=0)
        c.setFillColor(GOLD)
        c.rect(self.right - 2.2 * mm, y - 11 * mm, 2.2 * mm, 11 * mm, fill=1, stroke=0)
        title = self.rep.title + " — " + self.rep.unit_ar
        size = 12.0
        while size > 8 and self.width(shape(title), "NU-Bold", size) > self.right - self.left - 10 * mm:
            size -= 0.5
        self.text_r(title, self.right - 5 * mm, y - 7.3 * mm, "NU-Bold", size, white)
        self.y = y - 17 * mm
        # تذييل
        c.setStrokeColor(HexColor("#DCE3EC"))
        c.line(self.left, MARGIN + 8 * mm, self.right, MARGIN + 8 * mm)
        self.text_r("جميع النتائج محاكاة افتراضية وليست قياسات فعلية — لا تعني اعتماد جامعة نجران للمنصة.",
                    self.right, MARGIN + 3.5 * mm, size=7.5, color=MUTED)
        self.text_l(f"{self.page}  |  {self.rep.generated}", self.left, MARGIN + 3.5 * mm, size=7.5, color=MUTED)

    # ---- blocks -----------------------------------------------------------
    def heading(self, s):
        self.ensure(14 * mm)
        self.c.setFillColor(GOLD)
        self.c.rect(self.right - 1.6 * mm, self.y - 1.5 * mm, 1.6 * mm, 6 * mm, fill=1, stroke=0)
        self.text_r(s, self.right - 4 * mm, self.y, "NU-Bold", 12, NAVY)
        self.y -= 8 * mm

    def para(self, s, size=9.5, color=INK, font="NU-Regular", indent=0.0):
        maxw = self.right - self.left - indent
        for line in wrap(s, lambda t: self.width(t, font, size), maxw):
            self.ensure(size * 0.5 * mm + 4 * mm)
            self.text_r(line, self.right - indent, self.y, font, size, color)
            self.y -= size * 0.48 * mm + 1.6 * mm
        self.y -= 1.2 * mm

    def pairs(self, items, cols=2):
        colw = (self.right - self.left) / cols
        for i in range(0, len(items), cols):
            self.ensure(7 * mm)
            for j, (k, v) in enumerate(items[i:i + cols]):
                xr = self.right - j * colw
                self.text_r(f"{k}:", xr, self.y, "NU-Bold", 9, NAVY)
                kw = self.width(shape(f"{k}:"), "NU-Bold", 9)
                val = str(v)
                while self.width(shape(val), "NU-Regular", 9) > colw - kw - 6 * mm and len(val) > 4:
                    val = val[:-2]
                self.text_r(val, xr - kw - 2 * mm, self.y, "NU-Regular", 9, INK)
            self.y -= 6 * mm
        self.y -= 2 * mm

    def table(self, title, df, columns: dict, fmts: dict):
        self.heading(title)
        cols = list(columns)
        total = self.right - self.left
        # عرض الأعمدة: العمود النصي الأول أعرض
        weights = [2.4 if i == 0 else 1.0 for i in range(len(cols))]
        if "assessment" in cols:
            weights[cols.index("assessment")] = 2.2
        ws = [total * w / sum(weights) for w in weights]
        rowh = 6.6 * mm
        self.ensure(rowh * 2)
        self._row([columns[c] for c in cols], ws, rowh, header=True)
        for i, (_, r) in enumerate(df.iterrows()):
            if self.y - rowh < MARGIN + 14 * mm:
                self.new_page()
                self._row([columns[c] for c in cols], ws, rowh, header=True)
            vals = []
            for c in cols:
                v = r[c] if c in r.index else ""
                f = fmts.get(c)
                try:
                    vals.append(f.format(v) if f else str(v))
                except (ValueError, TypeError):
                    vals.append(str(v))
            self._row(vals, ws, rowh, alt=i % 2 == 1)
        self.y -= 5 * mm

    def _row(self, vals, ws, h, header=False, alt=False):
        c = self.c
        x = self.right
        if header or alt:
            c.setFillColor(NAVY if header else ROW_ALT)
            c.rect(self.left, self.y - h + 2 * mm, self.right - self.left, h, fill=1, stroke=0)
        font = "NU-Bold" if header else "NU-Regular"
        size = 8 if header else 8
        for v, w in zip(vals, ws):
            s = str(v)
            while self.width(shape(s), font, size) > w - 2.5 * mm and len(s) > 3:
                s = s[:-2] + "…" if not s.endswith("…") else s[:-3] + "…"
            self.text_r(s, x - 1.5 * mm, self.y - h / 2 + 2.6 * mm, font, size, white if header else INK)
            x -= w
        self.y -= h

    def finish(self) -> bytes:
        self.c.showPage()
        self.c.save()
        return self.buf.getvalue()


def build_pdf(rep: Report) -> bytes:
    w = _Writer(rep)
    w.para(rep.disclaimer, 8.5, MUTED)
    w.heading("السياق المؤسسي")
    w.pairs(rep.context)
    w.heading("إعدادات التجربة")
    w.pairs(rep.config)
    w.heading("المؤشرات الرئيسية (محسوبة)")
    w.pairs(rep.kpis)
    for t in rep.tables:
        w.table(*t)
    w.heading("التوصيات")
    if rep.recommendations:
        for i, (title, why, impact) in enumerate(rep.recommendations, 1):
            w.para(f"{i}. {title}", 10, NAVY, "NU-Bold")
            w.para(f"لماذا: {why}", 9, INK, indent=4 * mm)
            if impact:
                w.para(f"الأثر المتوقع (محاكاة): {impact}", 9, MUTED, indent=4 * mm)
    else:
        w.para("لم تتحقق شروط أي قاعدة توصية في هذه الإعدادات.")
    w.heading("الافتراضات")
    for a in rep.assumptions:
        w.para("• " + a, 9)
    return w.finish()
