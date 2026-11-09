"""
charts.py — رسوم Plotly مبنية كقواميس (dict) من نتائج الحساب مباشرة.

بناء الرسوم كقواميس يسمح باختبار بياناتها دون واجهة، ويتجنب مسارات عرض الجداول الثقيلة.
كل رسم: عنوان، وحدات على المحاور، وسيلة إيضاح مقروءة، وبيانات محسوبة فقط.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .theme import FONT_STACK, GOLD, GRAY, GREEN, INK, NAVY, NAVY_MID

STRATEGY_COLORS = {"R": "#6B7280", "A": NAVY_MID, "B": GOLD, "C": NAVY, "D": GREEN, "N": GRAY}
SERIES = [NAVY, GOLD, GREEN, NAVY_MID, GRAY, "#8A6A06"]


def _lst(x):
    if isinstance(x, (pd.Series, pd.Index)):
        x = x.to_numpy()
    if isinstance(x, np.ndarray):
        if np.issubdtype(x.dtype, np.datetime64):
            return [pd.Timestamp(v).strftime("%Y-%m-%d %H:%M") for v in x]
        return [None if (isinstance(v, float) and np.isnan(v)) else (v.item() if hasattr(v, "item") else v) for v in x]
    return list(x)


def base_layout(title: str, x_title: str = "", y_title: str = "", height: int = 380, **extra) -> dict:
    lay = {
        "title": {"text": title, "x": 0.99, "xanchor": "right", "font": {"size": 16, "color": NAVY}},
        "font": {"family": FONT_STACK, "size": 13, "color": INK},
        "paper_bgcolor": "#FFFFFF", "plot_bgcolor": "#FFFFFF",
        "margin": {"l": 60, "r": 30, "t": 70, "b": 55},
        "height": height,
        "legend": {"orientation": "h", "x": 1, "xanchor": "right", "y": 1.02, "yanchor": "bottom", "font": {"size": 12}},
        "xaxis": {"title": {"text": x_title}, "gridcolor": "#EDF1F6", "linecolor": "#C3D0E2", "zeroline": False},
        "yaxis": {"title": {"text": y_title}, "gridcolor": "#EDF1F6", "linecolor": "#C3D0E2", "zeroline": False},
        "hovermode": "x unified",
    }
    lay.update(extra)
    return lay


def comfort_band_shape(lo: float, hi: float) -> dict:
    return {"type": "rect", "xref": "paper", "yref": "y", "x0": 0, "x1": 1, "y0": lo, "y1": hi,
            "fillcolor": GREEN, "opacity": 0.10, "line": {"width": 0}, "layer": "below"}


def occupancy_shapes(ts, occ) -> list:
    """تظليل فترات الإشغال على محور الزمن."""
    ts = _lst(ts)
    occ = np.asarray(occ) > 0
    shapes, start = [], None
    for i, o in enumerate(occ):
        if o and start is None:
            start = i
        if (not o or i == len(occ) - 1) and start is not None:
            end = i if not o else i
            shapes.append({"type": "rect", "xref": "x", "yref": "paper", "x0": ts[start], "x1": ts[end],
                           "y0": 0, "y1": 1, "fillcolor": GOLD, "opacity": 0.08, "line": {"width": 0}, "layer": "below"})
            start = None
    return shapes


def temperature_chart(series: dict, t_out_df: pd.DataFrame, lo: float, hi: float, occ=None,
                      title="درجة الحرارة الداخلية مقابل الخارجية") -> dict:
    """series: {اسم: DataFrame(timestamp, t_in)} ؛ t_out_df: DataFrame(timestamp, t_out)."""
    data = [{"type": "scatter", "mode": "lines", "name": "الحرارة الخارجية",
             "x": _lst(t_out_df["timestamp"]), "y": _lst(t_out_df["t_out"].round(2)),
             "line": {"color": GRAY, "width": 2, "dash": "dot"},
             "hovertemplate": "%{y:.1f} °م"}]
    for i, (name, df) in enumerate(series.items()):
        color = df.attrs.get("color", SERIES[i % len(SERIES)])
        data.append({"type": "scatter", "mode": "lines", "name": name, "x": _lst(df["timestamp"]),
                     "y": _lst(df["t_in"].round(2)), "line": {"color": color, "width": 2.4,
                                                             "dash": df.attrs.get("dash", "solid")},
                     "hovertemplate": "%{y:.2f} °م"})
    shapes = [comfort_band_shape(lo, hi)]
    if occ is not None:
        shapes += occupancy_shapes(occ[0], occ[1])
    lay = base_layout(title, "الوقت", "درجة الحرارة (°م)", 420, shapes=shapes,
                      annotations=[{"text": f"نطاق الراحة الافتراضي {lo:.1f}–{hi:.1f} °م", "xref": "paper", "yref": "y",
                                    "x": 0.01, "y": hi, "xanchor": "left", "yanchor": "bottom", "showarrow": False,
                                    "font": {"size": 11, "color": "#00563F"}}])
    return {"data": data, "layout": lay}


def gains_chart(df: pd.DataFrame, title="المكاسب الحرارية وقدرة التبريد") -> dict:
    x = _lst(df["timestamp"])
    tr = [
        ("q_solar_w", "الكسب الشمسي", GOLD), ("q_internal_w", "الكسب الداخلي", NAVY_MID),
        ("q_envelope_w", "انتقال عبر الغلاف (موجب = كسب)", GRAY), ("q_cool_w", "التبريد المُزال", NAVY),
    ]
    data = [{"type": "scatter", "mode": "lines", "name": n, "x": x, "y": _lst((df[c] / 1000).round(3)),
             "line": {"color": col, "width": 2.6 if c == "q_cool_w" else 2, "shape": "hv" if c == "q_cool_w" else "linear"},
             "hovertemplate": "%{y:.2f} kW"} for c, n, col in tr]
    return {"data": data, "layout": base_layout(title, "الوقت", "القدرة الحرارية (kW)", 380)}


def bar_chart(categories, values, title, y_title, colors=None, text_fmt="{:.1f}", horizontal=False,
              x_title: str = "") -> dict:
    cats, vals = _lst(categories), [float(v) for v in values]
    colors = colors or [NAVY] * len(cats)
    tr = {"type": "bar", "marker": {"color": colors}, "text": [text_fmt.format(v) for v in vals],
          "textposition": "outside", "cliponaxis": False, "hovertemplate": "%{text}"}
    if horizontal:
        tr.update(x=vals, y=cats, orientation="h")
        lay = base_layout(title, y_title, x_title, max(300, 60 + 42 * len(cats)), hovermode="closest")
        lay["yaxis"]["autorange"] = "reversed"
    else:
        tr.update(x=cats, y=vals)
        lay = base_layout(title, x_title, y_title, 360, hovermode="closest")
    lay["showlegend"] = False
    return {"data": [tr], "layout": lay}


def grouped_bars(categories, groups: dict, title, y_title, colors=None, x_title="") -> dict:
    cats = _lst(categories)
    data = []
    for i, (name, vals) in enumerate(groups.items()):
        c = (colors or {}).get(name, SERIES[i % len(SERIES)])
        data.append({"type": "bar", "name": name, "x": cats, "y": [float(v) for v in vals],
                     "marker": {"color": c}, "hovertemplate": "%{y:.2f}"})
    return {"data": data, "layout": base_layout(title, x_title, y_title, 380, barmode="group", hovermode="closest")}


def stacked_bars(categories, parts: dict, title, y_title, colors=None, horizontal=True) -> dict:
    """أجزاء تُجمع إلى كلٍّ (مثل مكوّنات النقاط)."""
    cats = _lst(categories)
    data = []
    for i, (name, vals) in enumerate(parts.items()):
        c = (colors or {}).get(name, SERIES[i % len(SERIES)])
        tr = {"type": "bar", "name": name, "marker": {"color": c}, "hovertemplate": "%{x:.1f}" if horizontal else "%{y:.1f}"}
        if horizontal:
            tr.update(x=[float(v) for v in vals], y=cats, orientation="h")
        else:
            tr.update(x=cats, y=[float(v) for v in vals])
        data.append(tr)
    lay = base_layout(title, y_title if horizontal else "", "" if horizontal else y_title,
                      max(320, 80 + 44 * len(cats)), barmode="stack", hovermode="closest")
    if horizontal:
        lay["yaxis"]["autorange"] = "reversed"
    return {"data": data, "layout": lay}


def line_chart(x, ys: dict, title, x_title, y_title, colors=None, markers=True, dashes=None) -> dict:
    data = []
    for i, (name, vals) in enumerate(ys.items()):
        data.append({"type": "scatter", "mode": "lines+markers" if markers else "lines", "name": name,
                     "x": _lst(x), "y": [None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v) for v in vals],
                     "line": {"color": (colors or {}).get(name, SERIES[i % len(SERIES)]), "width": 2.4,
                              "dash": (dashes or {}).get(name, "solid")}})
    return {"data": data, "layout": base_layout(title, x_title, y_title, 380)}


def heatmap(z, x, y, title, colorbar_title, fmt=".1f") -> dict:
    zz = [[float(v) for v in row] for row in z]
    return {"data": [{"type": "heatmap", "z": zz, "x": _lst(x), "y": _lst(y),
                      "colorscale": [[0, "#F3F6FA"], [0.5, "#8FA6C6"], [1, NAVY]],
                      "texttemplate": "%{z:" + fmt + "}", "hovertemplate": "%{y} / %{x}: %{z:" + fmt + "}",
                      "colorbar": {"title": {"text": colorbar_title}}}],
            "layout": base_layout(title, "", "", 320, hovermode="closest")}


def scatter_points(points: pd.DataFrame, x, y, label, title, x_title, y_title, color_col=None, colors=None) -> dict:
    data = []
    groups = [(None, points)] if color_col is None else list(points.groupby(color_col))
    for i, (g, d) in enumerate(groups):
        data.append({"type": "scatter", "mode": "markers+text", "name": str(g) if g is not None else "",
                     "x": _lst(d[x]), "y": _lst(d[y]), "text": _lst(d[label]), "textposition": "top center",
                     "marker": {"size": 13, "color": (colors or {}).get(g, SERIES[i % len(SERIES)]),
                                "line": {"width": 1, "color": "#FFFFFF"}}})
    return {"data": data, "layout": base_layout(title, x_title, y_title, 420, hovermode="closest")}


def show(fig: dict, key: str | None = None) -> None:
    import streamlit as st
    kw = {"config": {"displaylogo": False, "responsive": True}}
    try:
        major, minor = (int(v) for v in st.__version__.split(".")[:2])
        if (major, minor) >= (1, 50):
            kw["width"] = "stretch"
        else:
            kw["use_container_width"] = True
    except Exception:  # noqa: BLE001
        kw["use_container_width"] = True
    if key:
        kw["key"] = key
    st.plotly_chart(fig, **kw)

