"""
scenarios.py — التجارب المعتمدة للنموذج الأولي (جداول بالساعات 0–24).

كل تجربة تحدد: الإشغال الفعلي (occupancy_blocks)، والجدول المعلن (timetable_blocks) الذي
تعتمد عليه الاستراتيجية B، وملف الطقس الافتراضي. عدد الطلاب أثناء الإشغال = params.occupancy
(صريح وقابل للتعديل في الواجهة). التظليل متغير متاح في كل التجارب.

سجل التعديل: أُبقيت المفاتيح الأربعة الأصلية (empty, prelecture, solar, overcool) لأنها تطابق
النطاق المعتمد، مع إضافة ملف الطقس الافتراضي ووصف الغرض العلمي، ودالة تخصيص الأوقات.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Scenario:
    key: str
    name_ar: str
    description_ar: str
    purpose_ar: str
    occupancy_blocks: tuple  # الإشغال الفعلي
    timetable_blocks: tuple  # الجدول المعلن (تعتمد عليه الاستراتيجية B)
    weather_profile: str = "typical"
    duration_h: int = 24


SCENARIOS = {
    "empty": Scenario(
        "empty", "القاعة الفارغة",
        "القاعة محجوزة في الجدول من 08:00 إلى 14:00 لكن لا يحضر أحد (عدد الطلاب = 0 طوال اليوم).",
        "الفصل بين المكاسب البيئية (الغلاف + الشمس) والمكاسب الداخلية، وكشف التشغيل غير الضروري "
        "عندما يعتمد التحكم على جدول ثابت بدل الإشغال الفعلي.",
        occupancy_blocks=(), timetable_blocks=((8.0, 14.0),),
    ),
    "prelecture": Scenario(
        "prelecture", "ما قبل المحاضرة",
        "القاعة خالية حتى بداية محاضرة واحدة (افتراضياً 12:00–14:00) ثم يحضر العدد المحدد من الطلاب دفعة واحدة.",
        "دراسة انتقال القاعة نحو ظروف الإشغال، وأثر التبريد المسبق على درجة الحرارة لحظة وصول الطلاب.",
        occupancy_blocks=((12.0, 14.0),), timetable_blocks=((12.0, 14.0),),
    ),
    "solar": Scenario(
        "solar", "كسب شمسي مرتفع",
        "محاضرات متتالية 08:00–16:00 في يوم صافٍ بإشعاع مرتفع. غيّر اتجاه النافذة والتظليل وخصائص الزجاج.",
        "تحليل أثر الاتجاه والإشعاع ومساحة النافذة و SHGC والتظليل على الكسب الشمسي وطلب التبريد.",
        occupancy_blocks=((8.0, 16.0),), timetable_blocks=((8.0, 16.0),),
        weather_profile="high_solar",
    ),
    "overcool": Scenario(
        "overcool", "الإفراط في التبريد",
        "الجدول المعلن 08:00–16:00 لكن المحاضرة الفعلية 10:00–11:30 فقط، مع مقارنة نقاط ضبط منخفضة (مثل 21°م).",
        "قياس الطاقة المستهلكة في تبريد غير ضروري (قاعة فارغة أو هدف أدنى من نطاق الراحة) وأثره على الراحة (برودة زائدة).",
        occupancy_blocks=((10.0, 11.5),), timetable_blocks=((8.0, 16.0),),
    ),
}


def customize(sc: Scenario, occupancy_blocks=None, timetable_blocks=None,
              weather_profile: str | None = None) -> Scenario:
    """نسخة من التجربة بأوقات/طقس مختلف (مع تحقق بسيط)."""
    for blocks in (occupancy_blocks, timetable_blocks):
        if blocks is None:
            continue
        for s, e in blocks:
            if not (0 <= s < e <= 24):
                raise ValueError("فترة زمنية غير صالحة: يجب 0 ≤ البداية < النهاية ≤ 24.")
    return replace(
        sc,
        occupancy_blocks=tuple(occupancy_blocks) if occupancy_blocks is not None else sc.occupancy_blocks,
        timetable_blocks=tuple(timetable_blocks) if timetable_blocks is not None else sc.timetable_blocks,
        weather_profile=weather_profile or sc.weather_profile,
    )
