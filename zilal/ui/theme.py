"""
theme.py — هوية جامعة نجران الرقمية للواجهة (مستخرجة من دليل الهوية BrandNU-2023).

من الدليل (صفحات 14، 20، 23): الأزرق الداكن #1C3D6A (يظهر #1D3D6A في صفحة الشعار)،
الذهبي العتيق #CC9E0A، الأخضر #009673، الرمادي #989898، والأبيض. الزخرفة: نمط خطوط رأسية
ومثلثات مستوحى من المبنى الإداري بالذهبي والأزرق. عناوين الأقسام: شريط أزرق بنص أبيض مع
خط ذهبي رأسي. الخطوط في الدليل (Al Mateen / Al Mohanad) للطباعة؛ للويب نستخدم Cairo.

قواعد الإتاحة: الذهبي والرمادي لا يُستخدمان لنص صغير على الأبيض (تباين غير كافٍ)؛ النص الأساسي
بالأزرق الداكن أو #1F2933.
"""
from __future__ import annotations

NAVY = "#1C3D6A"
GOLD = "#CC9E0A"
GREEN = "#009673"
GRAY = "#989898"
WHITE = "#FFFFFF"
INK = "#1F2933"          # نص أساسي عالي التباين
MUTED_INK = "#4A5568"    # نص ثانوي (تباين ≥ 7:1 على الأبيض)
NAVY_SOFT = "#E8EDF4"    # خلفيات خفيفة مشتقة من الأزرق
GOLD_SOFT = "#FBF4DE"
GREEN_SOFT = "#E3F4EF"
RED = "#B42318"          # للتحذيرات فقط (ليس من الهوية؛ ضروري دلالياً)
NAVY_MID = "#5B7AA6"

FONT_STACK = "'Cairo', 'Segoe UI', Tahoma, 'Noto Sans Arabic', Arial, sans-serif"

# نمط زخرفي هندسي بسيط (خطوط رأسية + مثلثات) بألوان الهوية — مستوحى من زخرفة الدليل، ليس الشعار.
_PATTERN_SVG = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='36' height='14' viewBox='0 0 36 14'>"
    "<path d='M0 0 L9 14 L18 0 Z' fill='%23CC9E0A'/>"
    "<path d='M18 0 L27 14 L36 0 Z' fill='%231C3D6A'/>"
    "</svg>"
)


def css() -> str:
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
:root {{ --nu-navy:{NAVY}; --nu-gold:{GOLD}; --nu-green:{GREEN}; --nu-gray:{GRAY}; --nu-ink:{INK}; }}
html, body, .stApp, [class*="css"], .stMarkdown, button, input, textarea, select, label {{
  font-family: {FONT_STACK} !important;
}}
.stApp {{ background: {WHITE}; color: {INK}; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container, [data-testid="stMainBlockContainer"] {{
  direction: rtl; text-align: right; max-width: 1240px; padding-top: 1.4rem; padding-bottom: 3rem;
}}
/* عناصر تحتاج اتجاه LTR لتعمل بشكل صحيح */
div[data-baseweb="slider"], .js-plotly-plot, .stPlotlyChart, [data-testid="stNumberInput"] input {{ direction: ltr; }}
p, li, label, .stMarkdown {{ line-height: 1.75; }}
h1, h2, h3, h4 {{ color: {NAVY}; font-weight: 700; }}

/* الشريط الجانبي */
section[data-testid="stSidebar"] {{ background: {NAVY}; direction: rtl; }}
section[data-testid="stSidebar"] * {{ color: #FFFFFF; }}
section[data-testid="stSidebar"] [data-baseweb="select"] * {{ color: {INK}; }}
section[data-testid="stSidebar"] [data-baseweb="select"] > div {{ background: #FFFFFF; }}
section[data-testid="stSidebar"] [role="radiogroup"] label {{
  padding: .35rem .6rem; border-radius: 6px; margin-bottom: 2px; width: 100%;
}}
section[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: rgba(255,255,255,.08); }}
section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.18); }}
.nu-logo-panel {{ background:#FFFFFF; border-radius:10px; padding:10px 12px; margin-bottom:.6rem; }}
.nu-side-label {{ font-size:.78rem; letter-spacing:.02em; opacity:.85; margin:.6rem 0 .2rem; }}
.nu-role-chip {{ display:inline-block; background:{GOLD}; color:{NAVY} !important; font-weight:700;
  border-radius:999px; padding:.05rem .7rem; font-size:.82rem; }}

/* رأس الصفحة */
.nu-page-head {{ border-bottom: 1px solid #DCE3EC; padding-bottom: .7rem; margin-bottom: 1rem; }}
.nu-page-head .eyebrow {{ color:{MUTED_INK}; font-size:.85rem; font-weight:600; }}
.nu-page-head h1 {{ font-size: 1.75rem; margin: .1rem 0 .2rem; color:{NAVY}; }}
.nu-page-head .sub {{ color:{MUTED_INK}; font-size: .98rem; margin:0; }}
.nu-pattern {{ height: 10px; background-image: url("{_PATTERN_SVG}"); background-repeat: repeat-x;
  background-size: 36px 10px; margin: .35rem 0 .2rem; opacity:.95; }}

/* عنوان قسم بنمط الدليل: شريط أزرق ونص أبيض وخط ذهبي */
.nu-section {{ display:flex; align-items:stretch; margin: 1.4rem 0 .7rem; }}
.nu-section .bar {{ width:6px; background:{GOLD}; border-radius:2px; margin-inline-end:8px; }}
.nu-section .label {{ background:{NAVY}; color:#FFFFFF; font-weight:700; padding:.35rem 1rem; border-radius:3px;
  font-size:1.05rem; }}

/* البطاقات */
.nu-cards {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin:.4rem 0 .8rem; }}
.nu-card {{ background:#FFFFFF; border:1px solid #DCE3EC; border-top:3px solid {NAVY}; border-radius:8px;
  padding:.75rem .9rem; min-height: 96px; }}
.nu-card.gold {{ border-top-color:{GOLD}; }} .nu-card.green {{ border-top-color:{GREEN}; }}
.nu-card.warn {{ border-top-color:{RED}; }}
.nu-card .k {{ color:{MUTED_INK}; font-size:.82rem; font-weight:600; }}
.nu-card .v {{ color:{NAVY}; font-size:1.55rem; font-weight:800; line-height:1.3; direction:ltr; unicode-bidi:plaintext; text-align:right; }}
.nu-card .u {{ color:{MUTED_INK}; font-size:.8rem; }}
.nu-card .s {{ color:{MUTED_INK}; font-size:.78rem; margin-top:.15rem; }}

/* شارات */
.nu-badge {{ display:inline-block; padding:.08rem .55rem; border-radius:4px; font-size:.78rem; font-weight:700;
  margin-inline-end:.35rem; vertical-align: middle; }}
.nu-badge.sim {{ background:{GOLD_SOFT}; color:#6B5205; border:1px solid #E9D48F; }}
.nu-badge.ok {{ background:{GREEN_SOFT}; color:#00563F; border:1px solid #9FD8C7; }}
.nu-badge.bad {{ background:#FDECEA; color:{RED}; border:1px solid #F4B7B0; }}
.nu-badge.info {{ background:{NAVY_SOFT}; color:{NAVY}; border:1px solid #C3D0E2; }}

/* ملاحظات */
.nu-note {{ border-inline-start:4px solid {GOLD}; background:#FAFAF7; padding:.6rem .9rem; border-radius:4px;
  font-size:.92rem; margin:.4rem 0 .9rem; color:{INK}; }}
.nu-note.navy {{ border-inline-start-color:{NAVY}; background:{NAVY_SOFT}; }}
.nu-empty {{ border:1px dashed #C3D0E2; border-radius:8px; padding:1.2rem; text-align:center; color:{MUTED_INK}; }}

/* الجداول (HTML — دون الاعتماد على مكوّن الجداول التفاعلي) */
.nu-table-wrap {{ overflow-x:auto; margin:.3rem 0 1rem; border:1px solid #DCE3EC; border-radius:8px; }}
table.nu-table {{ width:100%; border-collapse:collapse; direction:rtl; font-size:.9rem; }}
table.nu-table th {{ background:{NAVY}; color:#FFFFFF; font-weight:700; padding:.5rem .6rem; text-align:right;
  white-space:nowrap; }}
table.nu-table td {{ padding:.45rem .6rem; border-bottom:1px solid #EDF1F6; color:{INK}; text-align:right; }}
table.nu-table td.num {{ direction:ltr; unicode-bidi:plaintext; font-variant-numeric: tabular-nums; }}
table.nu-table tr:nth-child(even) td {{ background:#F8FAFC; }}
table.nu-table tr.hl td {{ background:{GOLD_SOFT}; font-weight:700; }}

/* توصيات وبطاقات ترتيب */
.nu-rec {{ border:1px solid #DCE3EC; border-inline-start:5px solid {NAVY}; border-radius:8px; padding:.8rem 1rem; margin:.6rem 0; }}
.nu-rec.p1 {{ border-inline-start-color:{GOLD}; }}
.nu-rec h4 {{ margin:0 0 .3rem; font-size:1.05rem; }}
.nu-rec .why {{ color:{INK}; font-size:.93rem; }}
.nu-rec .imp {{ display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin-top:.5rem; font-size:.88rem; }}
.nu-rec .imp div {{ background:#F8FAFC; border-radius:6px; padding:.4rem .6rem; }}
.nu-podium {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(210px,1fr)); gap:12px; margin:.6rem 0 1rem; }}
.nu-pod {{ border-radius:10px; padding:.9rem 1rem; background:{NAVY}; color:#FFFFFF; position:relative; overflow:hidden; }}
.nu-pod .rank {{ font-size:2rem; font-weight:800; color:{GOLD}; line-height:1; }}
.nu-pod .name {{ font-weight:700; margin:.3rem 0; }}
.nu-pod .score {{ font-size:1.4rem; font-weight:800; }}
.nu-pod .meta {{ font-size:.8rem; opacity:.9; }}
.nu-pod::after {{ content:""; position:absolute; left:0; bottom:0; width:100%; height:8px;
  background-image:url("{_PATTERN_SVG}"); background-size:36px 8px; opacity:.9; }}
.nu-meter {{ height:8px; background:#EDF1F6; border-radius:4px; overflow:hidden; }}
.nu-meter > span {{ display:block; height:100%; background:{GREEN}; }}

/* الصفحة الرئيسية */
.nu-hero {{ display:grid; grid-template-columns: 1.4fr 1fr; gap: 28px; align-items:center; margin: .4rem 0 1rem; }}
.nu-hero h1 {{ font-size:2.1rem; line-height:1.45; margin:.3rem 0 .6rem; }}
.nu-hero p {{ font-size:1.05rem; color:{INK}; }}
.nu-feature {{ border:1px solid #DCE3EC; border-radius:8px; padding:.7rem .9rem; }}
.nu-feature b {{ color:{NAVY}; }}
.nu-footer {{ margin-top:2.4rem; padding-top:.7rem; border-top:1px solid #DCE3EC; color:{MUTED_INK};
  font-size:.82rem; display:flex; justify-content:space-between; flex-wrap:wrap; gap:.5rem; }}
.nu-powered {{ font-size:.8rem; color:{MUTED_INK}; }}
.nu-powered b {{ color:{NAVY}; }}

div[data-testid="stMetric"] {{ background:#FFFFFF; border:1px solid #DCE3EC; border-radius:8px; padding:.6rem .8rem; }}
button[kind="primary"] {{ background:{NAVY}; border-color:{NAVY}; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
.stTabs [data-baseweb="tab"] {{ font-weight:600; }}
.stTabs [aria-selected="true"] {{ color:{NAVY}; }}
@media (max-width: 800px) {{
  .nu-hero {{ grid-template-columns: 1fr; }}
  .nu-rec .imp {{ grid-template-columns: 1fr; }}
  .nu-page-head h1 {{ font-size:1.4rem; }}
}}
</style>
"""
