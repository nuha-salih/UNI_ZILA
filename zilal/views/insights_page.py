"""
التحليلات والذكاء الاصطناعي — الخلاصة، الكهرباء (تكييف/إنارة)، الراحة والتوفير المؤهَّل، التنبؤ ودوره،
التوصيات، تحدي ظِلال، المنهجية، وتنزيل التقارير. كل الأرقام من محاكاة الحرم نفسها (state.campus_run).
"""
from __future__ import annotations

import streamlit as st

from .. import campus, challenge
from ..aggregation import aggregate
from ..engine.strategies import STRATEGY_NAMES_AR
from ..ml import FEATURES_AR
from ..reports.csv_export import summary_csv, timeseries_csv
from ..reports.pdf_report import build_pdf
from ..reports.report_data import unit_report
from ..ui import components as ui
from ..ui import state
from ..ui.site import icon

TH = campus.COMFORT_THRESHOLD
C_H, C_L, C_HB, C_LB = "#3B82C4", "#E8C766", "#9DBBDD", "#F2DFA3"


def _room_label(rid: str) -> str:
    r = campus.ROOM_BY_ID[rid]
    return f"{r.name_ar.split(' ')[1]} · {campus.BUILDING_BY_ID[r.building_id].name_ar.split(' ')[-1]}"


def _mode_label(rid: str) -> str:
    r = campus.ROOM_BY_ID[rid]
    s = STRATEGY_NAMES_AR[r.mode.strategy]
    return s + (f"، هدف ‎{r.mode.target_c:g} °م‎" if r.mode.target_c is not None else "")


@st.cache_data(show_spinner="جارٍ إعداد التقرير…")
def _report_files(level: str, unit: str | None):
    rep = unit_report(level, unit)
    return build_pdf(rep), summary_csv(rep), timeseries_csv(rep)


def _kpis(agg, sub) -> None:
    e, h, lt = agg["energy_kwh"], agg["hvac_kwh"], agg["lighting_kwh"]
    rb, rh, rl = agg["reference_energy_kwh"], agg["reference_hvac_kwh"], agg["reference_lighting_kwh"]
    bad = int((sub["comfort_compliance"] < TH - 1e-9).sum())
    raw = agg["saving_vs_reference_pct"]
    bad_txt = (f"يشمل {bad} {'قاعة' if bad == 1 else 'قاعات'} راحتها غير مقبولة، فلا يُعدّ كله توفيراً" if bad
               else "كل القاعات هنا حافظت على الراحة")
    ui.md(f"""<section aria-label="الخلاصة" class="z-grid4" style="margin:4px 0 18px">
<div class="z-kpi"><span class="k">الكهرباء الكلية اليوم</span><span class="v"><bdi>{e:.1f}</bdi> <small>kWh</small></span>
<div class="z-split" aria-hidden="true"><div style="width:{h / max(e, 1e-9) * 100:.1f}%;background:{C_H}"></div><div style="flex:1;background:{C_L}"></div></div>
<span class="s">تكييف <bdi>{h:.1f}</bdi> · إنارة <bdi>{lt:.1f}</bdi></span></div>
<div class="z-kpi"><span class="k">لو عملت بالتشغيل التقليدي</span><span class="v" style="color:#4A5568"><bdi>{rb:.1f}</bdi> <small>kWh</small></span>
<div class="z-split" aria-hidden="true"><div style="width:{rh / max(rb, 1e-9) * 100:.1f}%;background:{C_HB}"></div><div style="flex:1;background:{C_LB}"></div></div>
<span class="s">تكييف <bdi>{rh:.1f}</bdi> · إنارة <bdi>{rl:.1f}</bdi></span></div>
<div class="z-kpi"><span class="k">الفرق الخام</span><span class="v" style="color:#1F2933"><bdi>{-raw:+.1f}%</bdi></span>
<span class="s"><bdi>{rb - e:.1f} kWh</bdi> · {bad_txt}</span></div>
<div class="z-kpi navy"><span class="k">التوفير المؤهَّل (راحة ≥ 95%)</span><span class="v"><bdi>{agg["qualified_saving_pct"]:.1f}%</bdi></span>
<span class="s"><bdi>{agg["qualified_saving_kwh"]:.1f} kWh</bdi> من <bdi>{agg["qualified_rooms"]}</bdi> من <bdi>{len(sub)}</bdi> · من الاستهلاك التقليدي</span></div>
</section>""")


def _bars(units) -> None:
    mx = max(float(units["reference_energy_kwh"].max()), float(units["energy_kwh"].max()), 1e-9) * 1.02
    rows = []
    for _, u in units.iterrows():
        rows.append(f"""<div class="z-bar-row"><span class="nm">{ui.esc(u["unit_ar"])}</span><div>
<div class="z-bar"><div class="b" style="width:{u["energy_kwh"] / mx * 100:.1f}%"><div style="flex:{u["hvac_kwh"]:.3f};background:{C_H}"></div><div style="flex:{u["lighting_kwh"]:.3f};background:{C_L}"></div></div><b style="font-size:13px"><bdi>{u["energy_kwh"]:.1f} kWh</bdi></b></div>
<div class="z-bar"><div class="b" style="width:{u["reference_energy_kwh"] / mx * 100:.1f}%"><div style="flex:{u["reference_hvac_kwh"]:.3f};background:{C_HB}"></div><div style="flex:{u["reference_lighting_kwh"]:.3f};background:{C_LB}"></div></div><span class="z-muted" style="font-size:13px"><bdi>{u["reference_energy_kwh"]:.1f}</bdi></span></div>
</div></div>""")
    ui.md(f"""<div class="z-legend" style="margin-bottom:12px"><span><i style="background:{C_H}"></i>تكييف</span><span><i style="background:{C_L}"></i>إنارة</span>
<span><i style="background:{C_HB}"></i>التقليدي (فاتح)</span></div><div class="z-bars">{"".join(rows)}</div>
<p class="z-muted" style="font-size:13px;margin:12px 0 0">الشريط الداكن = التشغيل الحالي لكل قاعة، والفاتح = لو عملت القاعات نفسها بالتشغيل التقليدي تحت الظروف نفسها.</p>""")


def _comfort_table(sub) -> None:
    rows = []
    for rid, m in sub.iterrows():
        e, rb, c = m["energy_kwh"], m["reference_energy_kwh"], m["comfort_compliance"]
        d = (e - rb) / rb * 100 if rb > 1e-9 else 0.0
        if c < TH - 1e-9:
            tag, order = '<span class="z-tag bad">لا يُحتسب — الراحة دون 95%</span>', 3
        elif d < -0.5:
            tag, order = '<span class="z-tag ok">توفير مؤهَّل</span>', 0
        elif d > 0.5:
            tag, order = '<span class="z-tag gold">استهلاك أعلى</span>', 2
        else:
            tag, order = '<span class="z-tag mut">مماثل للتقليدي</span>', 1
        dc = "color:#B42318;font-weight:800" if d > 0.5 else ("color:#4A5568" if c < TH - 1e-9 else "")
        cc = "color:#B42318;font-weight:800" if c < TH - 1e-9 else ""
        rows.append((order, d, f"""<tr><td style="font-weight:800">{ui.esc(_room_label(rid))}</td><td>{ui.esc(_mode_label(rid))}</td>
<td class="c"><bdi>{e:.1f} / {rb:.1f}</bdi></td><td class="c" style="{dc}"><bdi>{d:+.1f}%</bdi></td>
<td class="c" style="{cc}"><bdi>{c * 100:.0f}%</bdi></td><td>{tag}</td></tr>"""))
    rows.sort(key=lambda x: (x[0], x[1]))
    ui.md(f"""<div class="z-tw"><table class="z-table"><thead><tr><th>القاعة</th><th>التشغيل</th><th style="text-align:center">الكهرباء / التقليدي (kWh)</th>
<th style="text-align:center">الفرق</th><th style="text-align:center">الراحة</th><th>الحكم</th></tr></thead><tbody>{"".join(r[2] for r in rows)}</tbody></table></div>""")


def _ai() -> None:
    room = campus.ROOM_BY_ID[campus.REFERENCE_ROOM]
    res = state.ml_result(room.room_id, room.mode.strategy)
    mt = res["metrics"]
    imp = res["importances"]["rf"].sort_values(ascending=False).head(4)
    mx = float(mt["MAE_kW"].max())

    def row(k, name, color, bold):
        w = "800" if bold else "700"
        return (f'<span style="font-weight:{w}">{name}</span><div class="z-meter"><span style="width:{mt.loc[k, "MAE_kW"] / mx * 100:.1f}%;'
                f'background:{color}"></span></div><span dir="ltr" style="font-weight:{w}">{mt.loc[k, "MAE_kW"]:.3f} kW</span>')
    chips = "".join(f'<span class="z-tag mut" style="margin:0 0 6px 6px">{ui.esc(n)} · {v * 100:.0f}%</span>' for n, v in imp.items())
    sp = res["split"]
    ui.md(f"""<div class="z-grid2"><div style="display:flex;flex-direction:column;gap:12px">
<div class="z-pt" style="margin:0"><span class="i" style="background:#E3F4EF;color:#00563F;flex-basis:26px;height:26px;border-radius:50%">✓</span><p><strong>يتنبأ</strong> بقدرة التكييف الكهربائية لكل 15 دقيقة لليوم التالي، لتخطيط الأحمال والتنبيه للذروة.</p></div>
<div class="z-pt" style="margin:0"><span class="i" style="background:#FDECEA;color:#B42318;flex-basis:26px;height:26px;border-radius:50%">✕</span><p><strong>لا يتحكم</strong> بالمكيّف. قرار التبريد المسبق يأتي من النموذج الحراري الفيزيائي.</p></div>
<div class="z-pt" style="margin:0"><span class="i" style="background:#FBF4DE;color:#6B5205;flex-basis:26px;height:26px;border-radius:50%">!</span><p><strong>مُدرَّب على بيانات اصطناعية</strong> ({sp["n_train"] // 96 + 1} يوماً تدريب من المحاكي): يقيس قدرته على تقليد المحاكي، لا دقته على قاعات حقيقية.</p></div>
<div>{chips}</div></div>
<div class="z-box" style="display:flex;flex-direction:column;gap:12px"><span style="font-size:14px;font-weight:800">متوسط الخطأ المطلق على أيام الاختبار اللاحقة (أقل = أفضل)</span>
<div class="z-mae">{row("rf", "Random Forest", "#1C3D6A", True)}{row("gb", "Gradient Boosting", "#5A7BA6", False)}{row("naive", "قيمة الأمس (مرجع)", "#989898", False)}</div>
<span class="z-muted" style="font-size:13px">R² = <bdi>{mt.loc["rf", "R2"]:.2f}</bdi> لـ Random Forest · تقسيم زمني بلا خلط: تدريب حتى <bdi>{sp["train_end"]:%Y-%m-%d}</bdi> ثم اختبار · القاعة {ui.esc(room.name_ar.split(" ")[1])} بالتشغيل {ui.esc(STRATEGY_NAMES_AR[room.mode.strategy])}</span></div></div>""")


def _recs(sub_ids) -> None:
    recs = [r for r in state.campus_recommendations() if r["room_id"] in sub_ids][:6]
    if not recs:
        ui.md('<p class="z-muted">لا توجد توصيات: كل القاعات في هذا النطاق تعمل بظِلال وحافظت على الراحة.</p>')
        return
    cards = []
    for r in recs:
        g = r["kind"] == "saving"
        col = "#00563F" if g else "#6B5205"
        cards.append(f"""<article class="z-rec{'' if g else ' gold'}"><span style="font-size:12px;font-weight:800;color:{col}">{'توفير مع راحة' if g else 'استعادة الراحة'}</span>
<h3>القاعة {ui.esc(_room_label(r["room_id"]))}: {ui.esc(r["title"])}</h3>
<span class="v" style="color:{col}"><bdi>{r["delta_kwh"]:+.1f} kWh</bdi> <span class="z-muted" style="font-size:13px;font-weight:600">يومياً</span></span>
<span class="z-muted" style="font-size:13px"><bdi>{r["energy_now"]:.1f} → {r["energy_new"]:.1f} kWh</bdi> · الراحة <bdi>{r["comfort_now"] * 100:.0f}% → {r["comfort_new"] * 100:.0f}%</bdi></span></article>""")
    ui.md(f'<div class="z-grid3">{"".join(cards)}</div><p class="z-muted" style="font-size:13px;margin:12px 0 0">'
          'كل أثر محسوب بإعادة محاكاة القاعة نفسها بالظروف نفسها. توصيات استعادة الراحة قد تزيد الكهرباء لأن الراحة تأتي أولاً.</p>')


def _challenge(m) -> None:
    board = challenge.room_leaderboard(m)
    digits = "٠١٢٣٤٥٦٧٨٩"
    items = []
    for i, r in board.iterrows():
        top = i == 0
        name = _room_label(r["room_id"]) + ("" if r["comfort_gate"] > 0 or r["eei"] <= 0.05 else " — توفير على حساب الراحة")
        items.append(f"""<li class="{'top' if top else ''}"><span class="r" style="{'color:#6B5205' if top else ''}">{digits[int(r["rank"])]}</span>
<span style="font-weight:800">القاعة {ui.esc(name)}</span><div class="z-meter" style="{'background:#FFFFFF' if top else ''}"><span style="width:{r["score"]:.1f}%;background:{'#CC9E0A' if top else '#1C3D6A'}"></span></div>
<span class="s"><bdi>{r["score"]:.1f}</bdi></span></li>""")
    ui.md(f"""<div style="display:flex;flex-wrap:wrap;gap:18px;align-items:flex-start"><ol class="z-lb" style="flex:999 1 520px;min-width:0">{"".join(items)}</ol>
<div class="z-box" style="flex:1 1 280px;display:flex;flex-direction:column;gap:8px;font-size:14px;line-height:1.7">
<strong style="font-size:15px;color:#1C3D6A">كيف تُحسب النقاط (من 100)</strong><span>نصف النقاط للراحة: نسبة الالتزام × 50.</span>
<span>نصفها للكهرباء مقابل التقليدي: توفير 50% أو أكثر = 50 نقطة.</span>
<span style="font-weight:800;color:#B42318">نقاط الكهرباء = صفر إذا قلّت الراحة عن 95%.</span>
<span class="z-muted" style="font-size:13px">كل قاعة تُقارن بنفسها تحت الظروف نفسها، فلا تُظلم القاعة الكبيرة. ترتيب تجريبي ببيانات محاكاة.</span></div></div>""")


def _method() -> None:
    ui.md("""<ul style="line-height:1.9;margin:0">
<li><b>النموذج الحراري:</b> نموذج RC أحادي المنطقة، تكامل أويلر بخطوة 900 ثانية (15 دقيقة)؛ معاملات القاعات افتراضات هندسية لا قياسات.</li>
<li><b>الكهرباء:</b> تكييف = Q_cool ÷ COP، وإنارة = كثافة الإنارة × المساحة عند التشغيل؛ الكلي = تكييف + إنارة. القدرة (kW) لحظية والطاقة (kWh) تكامل القدرة عبر الخطوات.</li>
<li><b>الإنارة:</b> 12 W/m² افتراض نموذج أولي؛ حرارتها تُضاف مرة واحدة إلى الكسب الداخلي فتزيد حمل التبريد (لا ازدواج).</li>
<li><b>التشغيل التقليدي (المرجع الوحيد):</b> تكييف بجدول ثابت 06:00–18:00 عند 24 °م، وإنارة 07:00–18:00 (افتراض عرض، ليس جدولاً موثّقاً للجامعة)، بتظليل القاعة وظروفها نفسها.</li>
<li><b>المقارنة العادلة:</b> الطقس والإشعاع والإشغال وخصائص القاعة والحرارة الابتدائية و COP والمدة متطابقة؛ يختلف التحكم فقط.</li>
<li><b>الراحة:</b> نطاق 22.5–25.5 °م أثناء الإشغال؛ القاعة مقبولة إذا التزمت ≥ 95% من ساعات الإشغال. التوفير المؤهَّل يجمع فرق القاعات المقبولة فقط.</li>
<li><b>الطقس:</b> يوم صيفي اصطناعي شبيه بنجران؛ حساسية COP ضمن 2.5–3.5. القاعات والمباني افتراضية لأغراض العرض.</li>
<li><b>الحدود:</b> لا اتصال بحساسات أو عدّادات أو أنظمة الجامعة؛ النتائج محاكاة وليست وفورات فعلية.</li></ul>""")


def render() -> None:
    run = state.campus_run()
    m = run["metrics"]
    top_l, top_r = st.columns([2, 1.2], vertical_alignment="bottom")
    with top_l:
        ui.md(f"""<h1 class="z-h1">التحليلات والذكاء الاصطناعي</h1>
<p class="z-muted" style="margin:0">{ui.esc(campus.CAMPUS_NAME_AR)}: {len(campus.BUILDINGS)} مبانٍ · {len(m)} قاعات · يوم صيفي اصطناعي · مقارنة بالتشغيل التقليدي تحت الظروف نفسها</p>""")
    with top_r:
        scope = st.radio("مستوى العرض", ["university", "building", "room"], horizontal=True, key="ins_scope",
                         format_func=lambda k: {"university": "الجامعة", "building": "المبنى", "room": "القاعة"}[k])
    unit = None
    if scope == "building":
        unit = st.selectbox("المبنى", [b.building_id for b in campus.BUILDINGS], key="ins_bld",
                            format_func=lambda b: campus.BUILDING_BY_ID[b].name_ar)
        sub = m[m["building_id"] == unit]
    elif scope == "room":
        unit = st.selectbox("القاعة", list(m.index), key="ins_room", index=list(m.index).index(campus.REFERENCE_ROOM),
                            format_func=lambda i: f"{campus.ROOM_BY_ID[i].name_ar} — {campus.BUILDING_BY_ID[campus.ROOM_BY_ID[i].building_id].name_ar}")
        sub = m.loc[[unit]]
    else:
        sub = m
    agg = aggregate(sub, "university", run["series"]).iloc[0]

    with st.expander("الخلاصة", expanded=True):
        _kpis(agg, sub)
    with st.expander("الكهرباء اليومية: تكييف وإنارة", expanded=True):
        _bars(aggregate(sub, "building" if scope == "university" else "room"))
    with st.expander("الراحة أولاً: أي توفير يُحتسب؟", expanded=True):
        ui.md(f'<p class="z-muted" style="font-size:13px;margin:0 0 8px">التزام بالراحة موزون: <strong><bdi>{agg["comfort_compliance"] * 100:.1f}%</bdi></strong> · الحد <bdi>95%</bdi> لكل قاعة</p>')
        _comfort_table(sub)
    with st.expander("التنبؤ بالذكاء الاصطناعي: ماذا يفعل وما لا يفعل", expanded=True):
        _ai()
    with st.expander("التوصيات — مرتبة بالأثر المحسوب", expanded=True):
        _recs(set(sub.index))
    with st.expander("تحدي ظِلال للاستدامة", expanded=True):
        _challenge(m)
    with st.expander("المنهجية والافتراضات", expanded=False):
        _method()

    level = {"university": "university", "building": "building", "room": "room"}[scope]
    ui.md("""<div class="z-card" style="margin-top:14px"><h2 class="z-h2" style="font-size:18px">تنزيل التقرير</h2>
<span class="z-muted" style="font-size:13px">الأرقام نفسها المعروضة هنا، مع الافتراضات وتنبيه البيانات الاصطناعية</span></div>""")
    if st.button("إعداد التقرير", key="ins_rep"):
        st.session_state["ins_rep_ready"] = (level, unit)
    if st.session_state.get("ins_rep_ready") == (level, unit):
        pdf, csv_s, csv_t = _report_files(level, unit)
        stem = f"zilal_{level}_{unit or 'ALL'}"
        c1, c2, c3 = st.columns(3)
        c1.download_button("PDF", pdf, file_name=f"{stem}.pdf", mime="application/pdf", type="primary", key="dl_pdf")
        c2.download_button("CSV ملخص", csv_s, file_name=f"{stem}_summary.csv", mime="text/csv", key="dl_csv")
        c3.download_button("CSV سلاسل زمنية", csv_t, file_name=f"{stem}_timeseries.csv", mime="text/csv", key="dl_ts")
