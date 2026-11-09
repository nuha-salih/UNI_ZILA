"""csv_export.py — تصدير CSV (UTF-8 مع BOM ليفتح بالعربية في Excel)."""
from __future__ import annotations

import io

import pandas as pd

from .report_data import Report


def summary_csv(rep: Report) -> bytes:
    """ملف واحد بأقسام: السياق، الإعدادات، المؤشرات، الجداول، التوصيات، التنبيه."""
    rows = [("section", "key", "value")]
    rows += [("meta", "title", rep.title), ("meta", "unit", rep.unit_ar), ("meta", "generated", rep.generated),
             ("meta", "data_label", "SIMULATED / SYNTHETIC — not measured")]
    rows += [("context", k, v) for k, v in rep.context]
    rows += [("config", k, v) for k, v in rep.config]
    rows += [("kpi", k, v) for k, v in rep.kpis]
    rows += [("recommendation", t, f"{w} | {i}") for t, w, i in rep.recommendations]
    rows += [("assumption", str(n), a) for n, a in enumerate(rep.assumptions, 1)]
    rows += [("disclaimer", "text", rep.disclaimer)]
    out = io.StringIO()
    pd.DataFrame(rows[1:], columns=rows[0]).to_csv(out, index=False)
    for title, df, cols, _ in rep.tables:
        out.write(f"\n# {title}\n")
        d = df.reset_index(drop=False) if df.index.name else df
        keep = [c for c in cols if c in d.columns]
        d[keep].rename(columns=cols).to_csv(out, index=False)
    return out.getvalue().encode("utf-8-sig")


def timeseries_csv(rep: Report) -> bytes:
    if rep.timeseries is None:
        return b""
    d = rep.timeseries.copy()
    d["data_label"] = "SIMULATED"
    return d.to_csv(index=False).encode("utf-8-sig")
