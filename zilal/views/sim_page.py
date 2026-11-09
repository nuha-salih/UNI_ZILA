"""
المحاكاة — القاعة الافتراضية 3D الحالية كما هي (classroom3d_v2) داخل هيكل الموقع.

المقارنة: التشغيل التقليدي المعتمد (campus.CONVENTIONAL_KEY) مقابل استراتيجية ظِلال، على مدخلات القاعة
بوضعها التشغيلي نفسه المستخدم في الرئيسية والتحليلات والتقارير. أي تعديل في الإعدادات يُعرض صراحةً كـ«ماذا لو».
"""
from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from .. import campus
from ..engine.evaluation import hhmm
from ..engine.strategies import STRATEGY_NAMES_AR
from ..engine.thermal_model import ORIENTATION_AR, ORIENTATIONS
from ..ui import components as ui
from ..ui import state
from ..ui.site import icon
from ..viz.classroom3d_compare import build_compare_state, render_html_v2

VIEWPORT_PX = 560
FRAME_PX = 1360  # القاعة + لوحة المقارنة الحية ورسم القدرة أسفلها (مع تمرير داخلي عند الحاجة)
START_INDEX = 32  # 08:00
KEYS = ("sim_zilal", "sim_students", "sim_shading", "sim_orientation", "sim_cop", "sim_lpd", "sim_light")


def _defaults(room) -> dict:
    p = room.params()
    return {"sim_zilal": campus.default_zilal_key(room), "sim_students": int(p.occupancy),
            "sim_shading": int(round(p.shading_fraction * 100)), "sim_orientation": p.orientation,
            "sim_cop": float(p.cop), "sim_lpd": float(p.lighting_w_per_m2),
            "sim_light": (float(p.lighting_on_h), float(p.lighting_off_h))}


def _reset(room_id: str | None = None) -> None:
    room = campus.ROOM_BY_ID[room_id or st.session_state.get("sim_room", campus.REFERENCE_ROOM)]
    for k, v in _defaults(room).items():
        st.session_state[k] = v


def _on_room() -> None:
    _reset(st.session_state["sim_room"])


def _overrides(room) -> tuple:
    d, ss, p = _defaults(room), st.session_state, room.params()
    out = {}
    if ss["sim_students"] != d["sim_students"]:
        out["occupancy"] = int(ss["sim_students"])
    if ss["sim_shading"] != d["sim_shading"]:
        out["shading_fraction"] = ss["sim_shading"] / 100.0
    if ss["sim_orientation"] != d["sim_orientation"]:
        out["orientation"] = ss["sim_orientation"]
    if abs(ss["sim_cop"] - d["sim_cop"]) > 1e-9:
        out["cop"] = float(ss["sim_cop"])
    if abs(ss["sim_lpd"] - d["sim_lpd"]) > 1e-9:
        out["lighting_w_per_m2"] = float(ss["sim_lpd"])
    if tuple(ss["sim_light"]) != tuple(d["sim_light"]):
        out["lighting_on_h"], out["lighting_off_h"] = (float(x) for x in ss["sim_light"])
    return tuple(sorted(out.items()))


def render() -> None:
    ss = st.session_state
    ss.setdefault("sim_room", campus.REFERENCE_ROOM)
    if any(k not in ss for k in KEYS):
        _reset()
    room = campus.ROOM_BY_ID[ss["sim_room"]]
    b = campus.BUILDING_BY_ID[room.building_id]

    top_l, top_r = st.columns([2.2, 1], vertical_alignment="bottom")
    with top_l:
        ui.md(f"""<span class="z-crumb">الحرم التجريبي › {ui.esc(b.name_ar)} › {ui.esc(room.floor_ar)}</span>
<h1 class="z-h1">{ui.esc(room.name_ar)} — يوم كامل: التقليدي مقابل ظِلال</h1>""")
    with top_r:
        st.selectbox("القاعة", [r.room_id for r in campus.ROOMS], key="sim_room", on_change=_on_room,
                     format_func=lambda i: f"{campus.ROOM_BY_ID[i].name_ar} — {campus.BUILDING_BY_ID[campus.ROOM_BY_ID[i].building_id].name_ar}")

    p0 = room.params()
    ui.md(f"""<div aria-label="ظروف المقارنة" style="margin:6px 0 4px">
<span class="z-chip">{icon("M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8zM12 2v2M12 20v2M2 12h2M20 12h2", 16, "#CC9E0A")}يوم صيفي اصطناعي شبيه بنجران</span>
<span class="z-chip">{icon("M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18zM12 7v5l3 2", 16, "#4A5568")}التقليدي: تكييف <bdi>06:00–18:00</bdi> عند <bdi>24 °م</bdi> · إنارة <bdi>{hhmm(p0.lighting_on_h)}–{hhmm(p0.lighting_off_h)}</bdi> (افتراض)</span>
<span class="z-chip">{icon("M3 17l6-6 4 4 8-8", 16, "#009673")}ظِلال: {ui.esc(STRATEGY_NAMES_AR[ss["sim_zilal"]])} · إنارة حسب الإشغال</span>
<span class="z-chip">{icon("M4 3h16v18H4zM4 9h16", 16, "#1C3D6A")}نفس القاعة والطقس والإشغال و COP للحالتين</span>
<span class="z-chip">الوضع التشغيلي لهذه القاعة: {ui.esc(room.mode.note_ar)}</span></div>""")

    main, side = st.columns([3.1, 1], gap="medium")
    with side:
        with st.form("sim_form", border=True):
            ui.md('<div style="font-weight:800;color:#1C3D6A;font-size:17px">إعدادات المحاكاة</div>')
            st.radio("استراتيجية ظِلال", ["D", "C"], key="sim_zilal", horizontal=True,
                     format_func=lambda k: {"D": "تنبؤي", "C": "عند الحضور"}[k])
            st.slider("عدد الطلاب", 0, room.capacity, key="sim_students")
            st.slider("التظليل (%)", 0, 100, step=5, key="sim_shading")
            st.radio("اتجاه النافذة", list(ORIENTATIONS), key="sim_orientation", horizontal=True,
                     format_func=lambda o: ORIENTATION_AR[o])
            with st.expander("افتراضات متقدمة"):
                st.slider("كفاءة المكيّف COP", 2.5, 3.5, step=0.1, key="sim_cop")
                st.slider("كثافة الإنارة (W/m²) — افتراض", 0.0, 25.0, step=0.5, key="sim_lpd")
                st.slider("جدول الإنارة التقليدي", 0.0, 24.0, step=0.5, key="sim_light")
            st.form_submit_button("تطبيق وإعادة الحساب", type="primary", use_container_width=True)
        st.button("العودة للوضع التشغيلي للقاعة", on_click=_reset, use_container_width=True, key="sim_reset")
        ui.md('<p class="z-muted" style="font-size:12px;line-height:1.7">كل رقم في القاعة يُحسب في محرك Python. '
              'سرعة العرض لا تغيّر خطوة الحساب ولا النتائج.</p>')

    ov = _overrides(room)
    try:
        lo, hi = ss["sim_light"]
        if not lo < hi:
            raise ValueError("جدول الإنارة غير صالح: يجب أن تسبق بداية التشغيل نهايته.")
        a = state.room_comparison(room.room_id, ss["sim_zilal"], ov)
        payload = build_compare_state(a, campus.CONVENTIONAL_KEY, ss["sim_zilal"], START_INDEX)
    except ValueError as exc:
        with main:
            st.error(f"تعذّر تشغيل المحاكاة: {exc}")
        return
    with main:
        if ov or ss["sim_zilal"] != campus.default_zilal_key(room):
            ui.note("وضع «ماذا لو»: الإعدادات الحالية تختلف عن الوضع التشغيلي للقاعة، لذلك قد تختلف هذه الأرقام عن "
                    "الرئيسية والتحليلات. زر «العودة للوضع التشغيلي للقاعة» يعيدها.")
        components.html(render_html_v2(payload, VIEWPORT_PX), height=FRAME_PX, scrolling=True)

    ui.md("""<section aria-label="جولة سريعة" class="z-card" style="margin-top:14px;display:flex;flex-direction:column;gap:12px">
<h2 class="z-h2" style="font-size:17px">جولة الدقائق الثلاث للمحكّم</h2><ol class="z-tour">
<li><span class="d">١</span><span>اضغط «ابدأ المحاكاة» من <bdi>08:00</bdi></span></li>
<li><span class="d">٢</span><span>اختر السرعة <bdi>5×</bdi> وشاهد التبريد المسبق</span></li>
<li><span class="d">٣</span><span>أوقف عند <bdi>12:00</bdi> وبدّل بين التقليدي وظِلال</span></li>
<li><span class="d g">٤</span><span>أكمل حتى <bdi>24:00</bdi> واقرأ النتيجة النهائية</span></li></ol></section>
<a href="?p=insights" target="_self" class="z-btn line" style="margin-top:14px">كيف تبدو النتائج على مستوى المبنى والجامعة؟ ←</a>""")
