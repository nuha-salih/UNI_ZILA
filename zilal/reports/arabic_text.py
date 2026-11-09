"""
arabic_text.py — تشكيل الحروف العربية (أشكال العرض Presentation Forms-B) وترتيب ثنائي الاتجاه
مبسّط لسطر واحد، لاستخدامه في ملفات PDF (ReportLab يرسم الحروف من اليسار لليمين دون تشكيل).

لماذا وحدة خاصة؟ لتجنب مكتبات إضافية (arabic-reshaper / python-bidi) قد تحتوي ملفات
مترجمة تمنعها سياسات Windows Application Control. النطاق: نصوص التقارير (عربي + أرقام + وحدات لاتينية).
القيود: لا يدعم الحركات (تُحذف)، ولا تضمين اتجاهات متداخلة معقدة.
"""
from __future__ import annotations

import re

# الحرف: (منفصل، نهائي، ابتدائي، وسطي) — None عند عدم وجود الشكل (حروف لا تتصل بما بعدها)
FORMS = {
    "ء": ("ﺀ", None, None, None),
    "آ": ("ﺁ", "ﺂ", None, None),
    "أ": ("ﺃ", "ﺄ", None, None),
    "ؤ": ("ﺅ", "ﺆ", None, None),
    "إ": ("ﺇ", "ﺈ", None, None),
    "ئ": ("ﺉ", "ﺊ", "ﺋ", "ﺌ"),
    "ا": ("ﺍ", "ﺎ", None, None),
    "ب": ("ﺏ", "ﺐ", "ﺑ", "ﺒ"),
    "ة": ("ﺓ", "ﺔ", None, None),
    "ت": ("ﺕ", "ﺖ", "ﺗ", "ﺘ"),
    "ث": ("ﺙ", "ﺚ", "ﺛ", "ﺜ"),
    "ج": ("ﺝ", "ﺞ", "ﺟ", "ﺠ"),
    "ح": ("ﺡ", "ﺢ", "ﺣ", "ﺤ"),
    "خ": ("ﺥ", "ﺦ", "ﺧ", "ﺨ"),
    "د": ("ﺩ", "ﺪ", None, None),
    "ذ": ("ﺫ", "ﺬ", None, None),
    "ر": ("ﺭ", "ﺮ", None, None),
    "ز": ("ﺯ", "ﺰ", None, None),
    "س": ("ﺱ", "ﺲ", "ﺳ", "ﺴ"),
    "ش": ("ﺵ", "ﺶ", "ﺷ", "ﺸ"),
    "ص": ("ﺹ", "ﺺ", "ﺻ", "ﺼ"),
    "ض": ("ﺽ", "ﺾ", "ﺿ", "ﻀ"),
    "ط": ("ﻁ", "ﻂ", "ﻃ", "ﻄ"),
    "ظ": ("ﻅ", "ﻆ", "ﻇ", "ﻈ"),
    "ع": ("ﻉ", "ﻊ", "ﻋ", "ﻌ"),
    "غ": ("ﻍ", "ﻎ", "ﻏ", "ﻐ"),
    "ف": ("ﻑ", "ﻒ", "ﻓ", "ﻔ"),
    "ق": ("ﻕ", "ﻖ", "ﻗ", "ﻘ"),
    "ك": ("ﻙ", "ﻚ", "ﻛ", "ﻜ"),
    "ل": ("ﻝ", "ﻞ", "ﻟ", "ﻠ"),
    "م": ("ﻡ", "ﻢ", "ﻣ", "ﻤ"),
    "ن": ("ﻥ", "ﻦ", "ﻧ", "ﻨ"),
    "ه": ("ﻩ", "ﻪ", "ﻫ", "ﻬ"),
    "و": ("ﻭ", "ﻮ", None, None),
    "ى": ("ﻯ", "ﻰ", None, None),
    "ي": ("ﻱ", "ﻲ", "ﻳ", "ﻴ"),
}
TATWEEL = "ـ"
LAM_ALEF = {"آ": ("ﻵ", "ﻶ"), "أ": ("ﻷ", "ﻸ"),
            "إ": ("ﻹ", "ﻺ"), "ا": ("ﻻ", "ﻼ")}
HARAKAT = re.compile("[ً-ْٰ]")
MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<", "«": "»", "»": "«"}
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _joins_next(ch: str) -> bool:
    """هل يتصل الحرف بما بعده (يملك شكلاً ابتدائياً/وسطياً)؟"""
    if ch == TATWEEL:
        return True
    f = FORMS.get(ch)
    return bool(f and f[2] is not None)


def _joins_prev(ch: str) -> bool:
    return ch == TATWEEL or (ch in FORMS and FORMS[ch][1] is not None)


def shape(text: str) -> str:
    """يحوّل النص العربي المنطقي إلى أشكال العرض المتصلة (بالترتيب المنطقي نفسه)."""
    t = HARAKAT.sub("", text)
    out = []
    i, n = 0, len(t)
    while i < n:
        ch = t[i]
        prev = t[i - 1] if i > 0 else ""
        connect_prev = bool(prev) and _joins_next(prev) and _joins_prev(ch)
        # لام + ألف
        if ch == "ل" and i + 1 < n and t[i + 1] in LAM_ALEF:
            iso, fin = LAM_ALEF[t[i + 1]]
            out.append(fin if connect_prev else iso)
            i += 2
            continue
        if ch not in FORMS:
            out.append(ch)
            i += 1
            continue
        nxt = t[i + 1] if i + 1 < n else ""
        connect_next = bool(nxt) and _joins_next(ch) and (_joins_prev(nxt) or nxt == "ل")
        iso, fin, ini, med = FORMS[ch]
        if connect_prev and connect_next and med:
            out.append(med)
        elif connect_prev and fin:
            out.append(fin)
        elif connect_next and ini:
            out.append(ini)
        else:
            out.append(iso)
        i += 1
    return "".join(out)


# أقواس لا تدخل في المقاطع اللاتينية: تبقى في السياق العربي فتُعكس صحيحاً حول المقطع
_LTR_RUN = re.compile(r"[+\-−]?[A-Za-z0-9][A-Za-z0-9 .,:;/%٪°²³+\-−–×=_·'\"@#&]*[A-Za-z0-9%٪°²³]|[A-Za-z0-9]")


def is_rtl(text: str) -> bool:
    return any("؀" <= c <= "ۿ" or "ﹰ" <= c <= "﻿" for c in text)


def visual(text: str) -> str:
    """سطر واحد → ترتيب بصري (للرسم من اليسار لليمين) باتجاه أساسي من اليمين لليسار."""
    text = text.translate(ARABIC_DIGITS)
    if not is_rtl(text):
        return text
    shaped = shape(text)
    segs, pos = [], 0
    for m in _LTR_RUN.finditer(shaped):
        if m.start() > pos:
            segs.append(("R", shaped[pos:m.start()]))
        segs.append(("L", m.group(0)))
        pos = m.end()
    if pos < len(shaped):
        segs.append(("R", shaped[pos:]))
    out = []
    for kind, s in reversed(segs):
        out.append(s if kind == "L" else "".join(MIRROR.get(c, c) for c in reversed(s)))
    return "".join(out)


def wrap(text: str, width_fn, max_width: float) -> list[str]:
    """تقسيم منطقي إلى أسطر بحسب عرض الأشكال المتصلة (width_fn يقيس نصاً مُشكّلاً)."""
    lines = []
    for para in str(text).split("\n"):
        words, cur = para.split(" "), ""
        for w in words:
            cand = (cur + " " + w).strip()
            if cur and width_fn(shape(cand)) > max_width:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        lines.append(cur)
    return lines
