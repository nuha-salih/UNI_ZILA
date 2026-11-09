"""
site.py — هيكل الموقع بثلاث صفحات (الرئيسية، المحاكاة، التحليلات والذكاء الاصطناعي) وفق التصميم المعتمد:
شريط علوي بالشعار الرسمي وثلاثة روابط، تذييل بتنبيه النموذج الأكاديمي، وأنماط بطاقات وأقسام موحّدة.
التنقل عبر معامل الرابط ?p=home|sim|insights (يعمل محلياً وعلى Streamlit Community Cloud دون تسجيل دخول).
"""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from . import components as ui

ROOT = Path(__file__).resolve().parents[2]
PAGES = {"home": "الرئيسية", "sim": "المحاكاة", "insights": "التحليلات والذكاء الاصطناعي"}
ICONS = {
    "home": "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
    "sim": "M12 2l9 5v10l-9 5-9-5V7zM12 22V12M21 7l-9 5-9-5",
    "insights": "M18 20V10M12 20V4M6 20v-6",
}


def icon(path: str, size: int = 18, color: str = "currentColor", width: float = 2) -> str:
    return (f'<svg aria-hidden="true" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"><path d="{path}"></path></svg>')


@st.cache_data(show_spinner=False)
def asset_b64(rel: str) -> str:
    p = ROOT / rel
    return base64.b64encode(p.read_bytes()).decode("ascii") if p.exists() else ""


def current_page() -> str:
    p = st.query_params.get("p", "home")
    return p if p in PAGES else "home"


def header(active: str) -> None:
    logo = asset_b64("brand/nu_logo_transparent.png")
    img = (f'<img src="data:image/png;base64,{logo}" alt="شعار جامعة نجران" class="z-logo">' if logo
           else '<span class="z-logo-ph">[شعار الجامعة]</span>')
    links = "".join(
        f'<a href="?p={k}" target="_self" class="z-nav-a{" on" if k == active else ""}"'
        f'{" aria-current=&quot;page&quot;" if k == active else ""}>{icon(ICONS[k])}{v}</a>'
        for k, v in PAGES.items())
    ui.md(f"""<header class="z-head"><div class="z-head-in">
<a href="?p=home" target="_self" class="z-brand">{img}<span class="z-brand-t"><b>منصة الأداء الحراري وكفاءة الطاقة</b>
<span>مدعوم بتقنية ظِلال AI</span></span></a>
<nav aria-label="التنقل الرئيسي" class="z-nav">{links}</nav>
<span class="z-proto">نموذج أكاديمي أولي · بيانات محاكاة</span></div></header>""")


def footer() -> None:
    ui.md("""<footer class="z-foot"><span>نموذج أكاديمي أولي ببيانات محاكاة اصطناعية — غير مرتبط رسمياً بأنظمة جامعة نجران
أو عدّادات مبانيها، ولا يعني اعتماد الجامعة للمنصة.</span><span>مدعوم بتقنية <b>ظِلال AI</b></span></footer>""")


def css() -> str:
    return """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] { display:none !important; }
header[data-testid="stHeader"] { height: 0; min-height: 0; }
.stApp { background:#F4F6F9; }
.block-container, [data-testid="stMainBlockContainer"] { max-width:1240px; padding-top:.5rem; }
.z-head { background:#FFFFFF; border:1px solid #DCE3EC; border-radius:14px; margin:.4rem 0 1.4rem; }
.z-head-in { padding:10px 18px; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:14px; }
.z-brand { display:flex; align-items:center; gap:14px; text-decoration:none !important; }
.z-logo { height:56px; width:auto; display:block; }
.z-brand-t { display:flex; flex-direction:column; border-inline-start:1px solid #DCE3EC; padding-inline-start:14px; line-height:1.45; }
.z-brand-t b { font-size:15px; color:#1C3D6A; } .z-brand-t span { font-size:12px; color:#4A5568; }
.z-nav { display:flex; flex-wrap:wrap; gap:4px; }
.z-nav-a { display:flex; align-items:center; gap:8px; padding:12px 16px; text-decoration:none !important; font-size:15px;
  font-weight:600; color:#4A5568 !important; border-bottom:3px solid transparent; }
.z-nav-a:hover { color:#1C3D6A !important; }
.z-nav-a.on { font-weight:800; color:#1C3D6A !important; border-bottom-color:#CC9E0A; }
.z-proto { font-size:12px; font-weight:700; color:#6B5205; background:#FBF4DE; border-radius:999px; padding:5px 12px; }
.z-foot { margin-top:2.4rem; padding:16px 4px; border-top:1px solid #DCE3EC; display:flex; flex-wrap:wrap;
  justify-content:space-between; gap:12px; font-size:13px; color:#4A5568; }
.z-foot b { color:#1C3D6A; }
.z-h1 { margin:0; font-size:30px; font-weight:800; color:#1C3D6A; line-height:1.4; }
.z-h2 { margin:0; font-size:22px; font-weight:800; color:#1C3D6A; }
.z-muted { color:#4A5568; font-size:14px; }
.z-crumb { color:#4A5568; font-size:13px; }
.z-card { background:#FFFFFF; border:1px solid #DCE3EC; border-radius:16px; padding:18px 20px; }
.z-grid4 { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px; }
.z-grid3 { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:14px; }
.z-grid2 { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:16px; }
.z-kpi { background:#FFFFFF; border:1px solid #DCE3EC; border-radius:16px; padding:18px; display:flex; flex-direction:column; gap:6px; }
.z-kpi .k { display:flex; align-items:center; gap:8px; font-size:14px; font-weight:700; color:#4A5568; }
.z-kpi .v { font-size:32px; font-weight:800; line-height:1.2; color:#1C3D6A; }
.z-kpi .v small { font-size:14px; font-weight:600; color:#4A5568; }
.z-kpi .s { font-size:13px; color:#4A5568; }
.z-kpi.good .v { color:#00563F; }
.z-kpi.navy { background:#1C3D6A; border-color:#1C3D6A; } .z-kpi.navy .k { color:#C9D4E4; }
.z-kpi.navy .v { color:#E8C766; } .z-kpi.navy .s { color:#DCE4EF; }
.z-split { display:flex; height:8px; border-radius:4px; overflow:hidden; direction:ltr; }
.z-chip { display:inline-block; background:#FFFFFF; border:1px solid #DCE3EC; border-radius:999px;
  padding:6px 14px; font-size:13px; font-weight:700; margin:0 0 6px 6px; line-height:1.6; max-width:100%; box-sizing:border-box; }
.z-chip svg { vertical-align:-3px; margin-inline-end:8px; }
.z-tag { display:inline-block; font-size:12px; font-weight:800; border-radius:999px; padding:3px 10px; white-space:nowrap; }
.z-tag.ok { color:#00563F; background:#E3F4EF; } .z-tag.bad { color:#B42318; background:#FDECEA; }
.z-tag.gold { color:#6B5205; background:#FBF4DE; } .z-tag.mut { color:#4A5568; background:#F0F3F7; }
.z-btn { display:inline-flex; align-items:center; gap:10px; text-decoration:none !important; border-radius:12px; padding:14px 26px;
  font-size:17px; font-weight:800; min-height:52px; box-sizing:border-box; }
.z-btn.gold { background:#CC9E0A; color:#1C2B40 !important; }
.z-btn.line { background:#FFFFFF; color:#1C3D6A !important; border:1px solid #C3D0E2; font-weight:700; font-size:16px; }
.z-hero { display:flex; flex-wrap:wrap; align-items:center; gap:40px; padding:18px 0 34px; }
.z-hero .txt { flex:1 1 440px; min-width:0; display:flex; flex-direction:column; gap:18px; }
.z-hero .eyebrow { align-self:flex-start; font-size:13px; font-weight:800; color:#1C3D6A; background:#E8EDF4; border-radius:999px; padding:5px 14px; }
.z-hero h1 { margin:0; font-size:42px; line-height:1.4; font-weight:800; color:#1C3D6A; }
.z-hero p { margin:0; font-size:18px; line-height:1.8; color:#4A5568; max-width:54ch; }
.z-hero figure { flex:1 1 500px; min-width:0; margin:0; display:flex; flex-direction:column; gap:10px; }
.z-hero img { width:100%; height:auto; display:block; border-radius:18px; border:1px solid #DCE3EC; box-shadow:0 16px 40px rgba(28,61,106,.12); }
.z-hero figcaption { font-size:13px; color:#4A5568; }
.z-pt { display:flex; gap:12px; align-items:flex-start; margin-top:14px; }
.z-pt .i { flex:0 0 40px; height:40px; border-radius:10px; display:flex; align-items:center; justify-content:center; }
.z-pt p { margin:0; font-size:16px; line-height:1.7; }
.z-steps { list-style:none; margin:0; padding:0; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px; }
.z-steps li { background:#FFFFFF; border:1px solid #DCE3EC; border-top:4px solid #1C3D6A; border-radius:14px; padding:18px;
  display:flex; flex-direction:column; gap:8px; }
.z-steps li.g { border-top-color:#CC9E0A; }
.z-steps .n { font-size:13px; font-weight:800; color:#6B5205; } .z-steps .t { font-size:16px; font-weight:800; }
.z-band { background:#1C3D6A; color:#FFFFFF; border-radius:16px; padding:32px 28px; display:flex; flex-wrap:wrap;
  align-items:center; justify-content:space-between; gap:20px; margin-top:8px; }
.z-band h2 { margin:0; font-size:26px; font-weight:800; color:#FFFFFF; } .z-band p { margin:4px 0 0; color:#DCE4EF; }
.z-tour { list-style:none; margin:0; padding:0; display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px; }
.z-tour li { display:flex; gap:10px; align-items:flex-start; font-size:14px; line-height:1.6; }
.z-tour .d { flex:0 0 28px; height:28px; border-radius:50%; background:#1C3D6A; color:#FFFFFF; display:flex;
  align-items:center; justify-content:center; font-size:13px; font-weight:800; }
.z-tour .d.g { background:#CC9E0A; color:#1C2B40; }
.z-bars { display:flex; flex-direction:column; gap:14px; }
.z-bar-row { display:grid; grid-template-columns:170px minmax(0,1fr); gap:12px; align-items:center; }
.z-bar-row .nm { font-size:15px; font-weight:800; }
.z-bar { display:flex; align-items:center; gap:10px; margin:3px 0; }
.z-bar .b { display:flex; height:18px; border-radius:4px; overflow:hidden; direction:ltr; }
.z-legend { display:flex; flex-wrap:wrap; gap:14px; font-size:13px; color:#4A5568; }
.z-legend i { display:inline-block; width:12px; height:12px; border-radius:3px; margin-inline-end:6px; vertical-align:-1px; }
table.z-table { width:100%; border-collapse:collapse; font-size:14px; min-width:760px; }
table.z-table th { text-align:start; padding:10px 8px; border-bottom:2px solid #DCE3EC; color:#4A5568; font-size:13px; }
table.z-table td { padding:10px 8px; border-bottom:1px solid #EDF1F6; }
table.z-table td.c { text-align:center; }
.z-tw { overflow-x:auto; }
.z-rec { border:1px solid #DCE3EC; border-top:4px solid #009673; border-radius:12px; padding:16px; display:flex;
  flex-direction:column; gap:8px; background:#FFFFFF; }
.z-rec.gold { border-top-color:#CC9E0A; }
.z-rec h3 { margin:0; font-size:16px; font-weight:800; color:#1F2933; }
.z-rec .v { font-size:26px; font-weight:800; }
.z-lb { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:8px; }
.z-lb li { display:grid; grid-template-columns:36px minmax(0,1fr) 160px 56px; gap:12px; align-items:center;
  border:1px solid #EDF1F6; border-radius:10px; padding:10px 12px; background:#FFFFFF; }
.z-lb li.top { background:#FBF4DE; border-color:#FBF4DE; }
.z-lb .r { font-size:18px; font-weight:800; color:#4A5568; } .z-lb .s { font-weight:800; font-size:17px; }
.z-meter { height:10px; background:#EDF1F6; border-radius:5px; direction:ltr; }
.z-meter span { display:block; height:10px; border-radius:5px; }
.z-mae { display:grid; grid-template-columns:150px minmax(0,1fr) 80px; gap:10px; align-items:center; font-size:14px; }
.z-box { background:#F7F9FC; border-radius:12px; padding:16px; }
[data-testid="stExpander"] details { background:#FFFFFF; border:1px solid #DCE3EC !important; border-radius:16px !important; }
[data-testid="stExpander"] summary p { font-size:19px !important; font-weight:800 !important; color:#1C3D6A !important; }
/* إخفاء عناصر الاستضافة وشارات المنشئ من الواجهة العامة */
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stAppDeployButton"],
[data-testid="appCreatorAvatar"], [class*="viewerBadge"], [class*="profileContainer"], [class*="profilePreview"] { display:none !important; }
.z-hero h1, .z-h1, .z-h2, .z-band h2, .z-steps .t, .z-rec h3 { overflow-wrap:anywhere; }
@media (max-width: 1024px) {
  [data-testid="stHorizontalBlock"] { flex-wrap:wrap !important; gap:1rem !important; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"], [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    flex:1 1 100% !important; width:100% !important; min-width:100% !important; }
  .z-hero { gap:28px; } .z-hero h1 { font-size:36px; } .z-hero figure { flex-basis:420px; }
  .z-lb li { grid-template-columns:36px minmax(0,1fr) 120px 56px; }
}
@media (max-width: 900px) {
  .z-grid4 { grid-template-columns:repeat(2, minmax(0,1fr)); }
  .z-grid3, .z-grid2 { grid-template-columns:1fr; }
  .z-steps, .z-tour { grid-template-columns:repeat(2, minmax(0,1fr)); }
  .z-hero h1 { font-size:30px; } .z-bar-row { grid-template-columns:1fr; gap:4px; }
  .z-lb li { grid-template-columns:30px minmax(0,1fr) 50px; } .z-lb li .z-meter { display:none; }
  .z-head-in { justify-content:center; } .z-nav { justify-content:center; }
}
@media (max-width: 640px) {
  .block-container, [data-testid="stMainBlockContainer"] { padding-left:1rem !important; padding-right:1rem !important; }
  .z-head { margin:.2rem 0 1rem; } .z-head-in { padding:10px 12px; gap:8px; }
  .z-brand { gap:10px; width:100%; justify-content:center; } .z-logo { height:44px; }
  .z-brand-t { padding-inline-start:10px; } .z-brand-t b { font-size:13.5px; } .z-brand-t span { font-size:11.5px; }
  .z-nav { width:100%; display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:2px; border-top:1px solid #EDF1F6; }
  .z-nav-a { flex-direction:column; justify-content:flex-start; gap:4px; padding:8px 2px; font-size:12.5px; line-height:1.4; text-align:center; }
  .z-proto { width:100%; text-align:center; font-size:11.5px; box-sizing:border-box; }
  .z-h1 { font-size:23px; } .z-h2 { font-size:19px; }
  .z-hero { gap:20px; padding:6px 0 22px; } .z-hero .txt { flex-basis:100%; gap:14px; } .z-hero figure { flex-basis:100%; }
  .z-hero h1 { font-size:26px; } .z-hero p { font-size:16px; }
  .z-btn { flex:1 1 100%; justify-content:center; padding:12px 18px; font-size:16px; min-height:48px; }
  .z-grid4 { gap:10px; } .z-kpi { padding:14px; } .z-kpi .v { font-size:25px; } .z-kpi .k { font-size:13px; } .z-kpi .s { font-size:12px; }
  .z-card { padding:16px !important; }
  .z-steps, .z-tour { grid-template-columns:1fr; }
  .z-band { padding:22px 18px; } .z-band h2 { font-size:20px; }
  .z-chip { font-size:12px; padding:5px 12px; margin:0 0 6px 4px; }
  .z-mae { grid-template-columns:110px minmax(0,1fr) 72px; font-size:13px; }
  .z-rec .v { font-size:22px; }
  .z-foot { flex-direction:column; gap:6px; font-size:12px; margin-top:1.6rem; }
  [data-testid="stExpander"] summary p { font-size:17px !important; }
  section[aria-label] { margin-bottom:24px !important; }
}
</style>
"""
