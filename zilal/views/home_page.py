"""الرئيسية — تعريف ظِلال، المشكلة والحل، مؤشرات قليلة محسوبة من المحرك، ودعوة لفتح المحاكاة."""
from __future__ import annotations

from .. import campus
from ..aggregation import aggregate
from ..ui import components as ui
from ..ui import site, state
from ..ui.site import icon


def _pct(new: float, old: float) -> str:
    return f"{(new - old) / old * 100:+.0f}%".replace("-", "−") if old > 1e-9 else "—"


def render() -> None:
    run = state.campus_run()
    m = run["metrics"]
    r = m.loc[campus.REFERENCE_ROOM]
    uni = aggregate(m, "university", run["series"]).iloc[0]
    room = campus.ROOM_BY_ID[campus.REFERENCE_ROOM]
    img = site.asset_b64("assets/classroom_preview.jpg")
    fig = (f'<figure><img src="data:image/jpeg;base64,{img}" alt="القاعة الافتراضية ثلاثية الأبعاد كما تظهر في صفحة المحاكاة">'
           f'<figcaption>معاينة القاعة الافتراضية {ui.esc(room.name_ar.split(" ")[1])} — تُفتح تفاعلياً في صفحة المحاكاة</figcaption></figure>'
           if img else "")
    ui.md(f"""<section class="z-hero"><div class="txt">
<span class="eyebrow">مشروع أكاديمي لقاعات جامعة نجران</span>
<h1>قاعة باردة حين يحضر الطلاب، وكهرباء أقل حين يغيبون</h1>
<p>ظِلال يتنبأ بحرارة القاعة ويبدأ التبريد في آخر لحظة مناسبة، ويطفئ الإنارة حين تفرغ القاعة، ولا يحتسب أي توفير إلا إذا بقيت الراحة الحرارية مقبولة.</p>
<div style="display:flex;flex-wrap:wrap;gap:12px">
<a href="?p=sim" target="_self" class="z-btn gold"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"></path></svg>افتح المحاكاة</a>
<a href="?p=insights" target="_self" class="z-btn line">التحليلات والنتائج</a></div></div>{fig}</section>""")

    comp = r["comfort_compliance"] * 100
    ui.md(f"""<section aria-label="أبرز النتائج" style="display:flex;flex-direction:column;gap:16px;margin-bottom:36px">
<div style="display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px">
<h2 class="z-h2">يوم واحد في القاعة {ui.esc(room.name_ar.split(" ")[1])}</h2>
<span class="z-muted" style="font-size:13px">مقارنة بالتشغيل التقليدي: تكييف ‎06:00–18:00‎ عند ‎24 °م‎، إنارة ‎07:00–18:00‎ (افتراض) · يوم صيفي اصطناعي</span></div>
<div class="z-grid4">
<div class="z-kpi good"><span class="k">{icon("M13 2L4 14h7l-1 8 9-12h-7z", 20, "#1C3D6A")}الكهرباء الكلية</span>
<span class="v"><bdi>{_pct(r["energy_kwh"], r["reference_energy_kwh"])}</bdi></span>
<span class="s"><bdi>{r["energy_kwh"]:.1f}</bdi> مقابل <bdi>{r["reference_energy_kwh"]:.1f} kWh</bdi> · تكييف + إنارة</span></div>
<div class="z-kpi good"><span class="k">{icon("M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z", 20, "#CC9E0A")}الإنارة</span>
<span class="v"><bdi>{_pct(r["lighting_kwh"], r["reference_lighting_kwh"])}</bdi></span>
<span class="s"><bdi>{r["lighting_kwh"]:.1f}</bdi> مقابل <bdi>{r["reference_lighting_kwh"]:.1f} kWh</bdi> · تعمل وقت المحاضرات فقط</span></div>
<div class="z-kpi {'good' if comp >= 95 else ''}"><span class="k">{icon("M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z", 20, "#009673")}الراحة أثناء المحاضرات</span>
<span class="v"><bdi>{comp:.0f}%</bdi></span>
<span class="s">الحد المطلوب <bdi>95%</bdi> · نطاق <bdi>22.5–25.5 °م</bdi></span></div>
<div class="z-kpi navy"><span class="k">{icon("M4 21V7l8-4 8 4v14M9 21v-4h6v4", 20, "#E8C766")}الحرم التجريبي ({len(m)} قاعات)</span>
<span class="v"><bdi>{uni["qualified_saving_pct"]:.1f}%</bdi></span>
<span class="s">توفير مؤهَّل: <bdi>{uni["qualified_rooms"]}</bdi> قاعات حافظت على الراحة · الفرق الخام <bdi>{uni["saving_vs_reference_pct"]:.1f}%</bdi></span></div>
</div></section>""")

    def pt(color_bg, color, path, html):
        return (f'<div class="z-pt"><span class="i" style="background:{color_bg};color:{color}">{icon(path, 20)}</span>'
                f'<p>{html}</p></div>')
    ui.md(f"""<section aria-label="المشكلة والحل" class="z-grid2" style="margin-bottom:36px">
<div class="z-card" style="padding:24px"><h2 class="z-h2" style="color:#B42318;display:flex;align-items:center;gap:10px">{icon("M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z", 24)}المشكلة</h2>
{pt("#FDECEA", "#B42318", "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18zM12 7v5l3 2", "<strong>تكييف بجداول ثابتة</strong> يعمل ساعات طويلة والقاعة فارغة، لأنه لا يعرف متى يحضر الطلاب.")}
{pt("#FDECEA", "#B42318", "M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z", "<strong>إنارة في قاعات فارغة</strong> تستهلك الكهرباء وتضيف حرارة يزيلها المكيّف لاحقاً.")}
{pt("#FDECEA", "#B42318", "M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z", "<strong>الترشيد الأعمى يضر الطلاب:</strong> إطفاء التكييف يوفر كهرباء لكنه يترك القاعة حارة وقت المحاضرة.")}
</div>
<div class="z-card" style="padding:24px"><h2 class="z-h2" style="color:#00563F;display:flex;align-items:center;gap:10px">{icon("M20 6L9 17l-5-5", 24, "currentColor", 2.4)}حل ظِلال</h2>
{pt("#E3F4EF", "#00563F", "M3 17l6-6 4 4 8-8M14 7h7v7", "<strong>تبريد مسبق محسوب:</strong> نموذج حراري فيزيائي يحدد آخر لحظة يبدأ فيها التبريد لتكون القاعة مريحة عند وصول الطلاب.")}
{pt("#E3F4EF", "#00563F", "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8a4 4 0 1 0 0 8z", "<strong>إنارة حسب الإشغال:</strong> تعمل حين يوجد طلاب وتنطفئ حين تفرغ القاعة.")}
{pt("#E3F4EF", "#00563F", "M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z", "<strong>توفير مؤهَّل فقط:</strong> لا يُحتسب أي توفير إذا قلّ الالتزام بالراحة عن <bdi>95%</bdi>.")}
</div></section>""")

    ui.md("""<section aria-label="كيف يعمل" style="display:flex;flex-direction:column;gap:16px;margin-bottom:36px">
<h2 class="z-h2">كيف يتخذ ظِلال القرار كل 15 دقيقة</h2><ol class="z-steps">
<li><span class="n">١ · يقرأ</span><span class="t">حرارة القاعة، الجدول الدراسي، توقع الطقس</span><span class="z-muted" style="font-size:13px">في النموذج الأولي: بيانات اصطناعية</span></li>
<li><span class="n">٢ · يتنبأ</span><span class="t">كيف ستتغير حرارة القاعة حتى وصول الطلاب</span><span class="z-muted" style="font-size:13px">نموذج حراري RC بخطوة 15 دقيقة</span></li>
<li><span class="n">٣ · يقرر</span><span class="t">متى يبدأ التبريد، ومتى تُطفأ الإنارة</span><span class="z-muted" style="font-size:13px">تبريد مسبق في آخر لحظة كافية</span></li>
<li class="g"><span class="n">٤ · يقيس</span><span class="t">الكهرباء والراحة معاً مقابل التشغيل التقليدي</span><span class="z-muted" style="font-size:13px">kW لحظياً، kWh تراكمياً</span></li>
</ol></section>""")
    ui.md(f"""<section class="z-band"><div><h2>شاهد يوماً كاملاً في القاعة {ui.esc(room.name_ar.split(" ")[1])} خلال دقائق</h2>
<p>شغّل الزمن، غيّر السرعة، وقارن التقليدي بظِلال لحظة بلحظة.</p></div>
<a href="?p=sim" target="_self" class="z-btn gold"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"></path></svg>افتح المحاكاة</a></section>""")
