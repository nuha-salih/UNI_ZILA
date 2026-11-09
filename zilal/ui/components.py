"""components.py — مكوّنات واجهة موحّدة (HTML آمن، بطاقات، جداول، شارات، ملاحظات)."""
from __future__ import annotations

import base64
import html
import math
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
LOGO_PATH = ROOT / "brand" / "nu_logo.png"


def esc(x) -> str:
    return html.escape(str(x))


def ltr(x) -> str:
    """عزل مقطع لاتيني/رقمي/معادلة داخل نص عربي (LRI … PDI) لمنع انعكاس ترتيبه."""
    return "\u2066" + str(x) + "\u2069"


def md(raw_html: str) -> None:
    st.markdown(raw_html, unsafe_allow_html=True)


def fmt_num(v, digits: int = 1, pct: bool = False, signed: bool = False) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return esc(v)
    if math.isnan(f):
        return "—"
    if pct:
        f *= 100
    s = f"{f:+,.{digits}f}" if signed else f"{f:,.{digits}f}"
    return s + ("٪" if pct else "")


def page_header(title: str, subtitle: str = "", eyebrow: str = "") -> None:
    md(f"""<div class="nu-page-head">
<div class="eyebrow">{esc(eyebrow)}</div><h1>{esc(title)}</h1>
<p class="sub">{esc(subtitle)}</p><div class="nu-pattern"></div></div>""")


def section(title: str) -> None:
    md(f'<div class="nu-section"><span class="bar"></span><span class="label">{esc(title)}</span></div>')


def badge(text: str, kind: str = "info") -> str:
    return f'<span class="nu-badge {kind}">{esc(text)}</span>'


def sim_badges(*extra: str) -> None:
    parts = [badge("نموذج أولي تجريبي", "sim"), badge("بيانات محاكاة", "sim")] + [badge(e, "info") for e in extra]
    md("<div>" + "".join(parts) + "</div>")


def note(text: str, kind: str = "") -> None:
    md(f'<div class="nu-note {kind}">{text}</div>')


def empty_state(text: str) -> None:
    md(f'<div class="nu-empty">{esc(text)}</div>')


def cards(items: Iterable[dict]) -> None:
    """items: dict(k=العنوان, v=القيمة النصية, u=الوحدة, s=سطر توضيحي, tone=''|'gold'|'green'|'warn')."""
    out = []
    for it in items:
        out.append(f"""<div class="nu-card {it.get('tone', '')}"><div class="k">{esc(it['k'])}</div>
<div class="v">{esc(it['v'])} <span class="u">{esc(it.get('u', ''))}</span></div>
<div class="s">{esc(it.get('s', ''))}</div></div>""")
    md('<div class="nu-cards">' + "".join(out) + "</div>")


def table(df: pd.DataFrame, columns: dict, formats: dict | None = None, highlight: Callable | None = None,
          index: bool = False) -> None:
    """
    جدول HTML ثابت (لا يعتمد على مكوّن st.dataframe/pyarrow).
    columns: {اسم العمود في df: العنوان العربي}. formats: {اسم العمود: دالة → نص}.
    """
    formats = formats or {}
    if df is None or len(df) == 0:
        empty_state("لا توجد بيانات لعرضها.")
        return
    d = df.reset_index() if index else df
    head = "".join(f"<th>{esc(v)}</th>" for v in columns.values())
    rows = []
    for _, r in d.iterrows():
        tds = []
        for c in columns:
            v = r[c] if c in r else ""
            if c in formats:
                txt, num = formats[c](v), True
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                txt, num = fmt_num(v, 2), True
            else:
                txt, num = esc(v), False
            tds.append(f'<td class="{"num" if num else ""}">{txt}</td>')
        cls = ' class="hl"' if highlight is not None and highlight(r) else ""
        rows.append(f"<tr{cls}>" + "".join(tds) + "</tr>")
    md(f'<div class="nu-table-wrap"><table class="nu-table"><thead><tr>{head}</tr></thead>'
       f'<tbody>{"".join(rows)}</tbody></table></div>')


def footer() -> None:
    md("""<div class="nu-footer"><span>نموذج أولي تجريبي مقترح — جميع البيانات والنتائج محاكاة افتراضية،
ولا تمثّل أداءً فعلياً لمباني جامعة نجران، ولا تعني اعتماد الجامعة للمنصة.</span>
<span class="nu-powered">مدعوم بتقنية <b>ظِلال AI</b></span></div>""")


@st.cache_data(show_spinner=False)
def _logo_b64() -> str | None:
    if not LOGO_PATH.exists():
        return None
    return base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")


def logo(max_width: int = 220) -> None:
    """الشعار الرسمي المزوَّد كما هو (بنسبه وألوانه، دون تعديل) على خلفية بيضاء؛ وإلا عنصر نائب محايد."""
    b64 = _logo_b64()
    if b64:
        md(f'<div class="nu-logo-panel"><img src="data:image/png;base64,{b64}" alt="شعار جامعة نجران" '
           f'style="display:block;width:100%;max-width:{max_width}px;height:auto;margin:0 auto;"/></div>')
    else:
        md('<div class="nu-logo-panel" style="color:#4A5568;text-align:center;">[موضع شعار الجامعة]</div>')
