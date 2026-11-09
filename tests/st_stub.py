"""
st_stub.py — بديل خفيف لواجهة Streamlit لاختبارات التكامل دون متصفح.

ينفّذ كل كود الصفحات فعلياً (الحسابات، بناء الرسوم والجداول، منطق الأدوار والقوائم المتتالية)
ويسجّل الاستدعاءات للتحقق منها. لا يختبر المظهر المرئي — ذلك يتطلب تشغيل Streamlit الحقيقي في متصفح.
"""
from __future__ import annotations

import sys
import types


class StopApp(Exception):
    pass


class SessionState(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v


class Recorder:
    def __init__(self):
        self.reset()

    def reset(self):
        self.calls = []
        self.figures = []
        self.errors = []
        self.exceptions = []
        self.downloads = []
        self.markdown = []
        self.widgets = {}
        self.clicks = set()
        self.components = []


REC = Recorder()


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Container(_Ctx):
    def __init__(self, st):
        self._st = st

    # ---- output ----
    def markdown(self, body, unsafe_allow_html=False, **kw):
        REC.markdown.append(str(body))

    def write(self, *a, **kw):
        REC.calls.append(("write", a))

    def caption(self, *a, **kw):
        REC.calls.append(("caption", a))

    def latex(self, s, **kw):
        REC.calls.append(("latex", s))

    def image(self, *a, **kw):
        REC.calls.append(("image", a))

    def plotly_chart(self, fig, **kw):
        REC.figures.append(fig)

    def metric(self, *a, **kw):
        REC.calls.append(("metric", a))

    def info(self, *a, **kw):
        REC.calls.append(("info", a))

    def success(self, *a, **kw):
        REC.calls.append(("success", a))

    def warning(self, *a, **kw):
        REC.calls.append(("warning", a))

    def error(self, msg, **kw):
        REC.errors.append(str(msg))

    def exception(self, exc, **kw):
        REC.exceptions.append(exc)

    def divider(self):
        pass

    # ---- layout ----
    def columns(self, spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [Container(self._st) for _ in range(n)]

    def tabs(self, labels):
        return [Container(self._st) for _ in labels]

    def expander(self, *a, **kw):
        return Container(self._st)

    def container(self, **kw):
        return Container(self._st)

    def spinner(self, *a, **kw):
        return _Ctx()

    def form(self, *a, **kw):
        return Container(self._st)

    def form_submit_button(self, label, key=None, on_click=None, **kw):
        return self.button(label, key=key, on_click=on_click)

    # ---- widgets ----
    def _store(self, key, default, label):
        ss = self._st.session_state
        k = key if key is not None else f"__w_{label}"
        if k not in ss:
            ss[k] = default
        REC.widgets[k] = label
        return ss[k]

    def selectbox(self, label, options, index=0, key=None, format_func=str, on_change=None, args=(), **kw):
        options = list(options)
        for o in options:
            format_func(o)
        ss = self._st.session_state
        if key is not None and key in ss and ss[key] in options:
            return ss[key]
        val = options[index] if options else None
        return self._store(key, val, label) if key is None or key not in ss else self._force(key, val)

    def _force(self, key, val):
        self._st.session_state[key] = val
        return val

    def radio(self, label, options, index=0, key=None, format_func=str, **kw):
        return self.selectbox(label, options, index=index, key=key, format_func=format_func)

    def multiselect(self, label, options, default=None, key=None, format_func=str, **kw):
        for o in options:
            format_func(o)
        return self._store(key, list(default or []), label)

    def slider(self, label, min_value=None, max_value=None, value=None, step=None, key=None, **kw):
        if value is None:
            value = min_value
        return self._store(key, value, label)

    def number_input(self, label, min_value=None, max_value=None, value=None, step=None, key=None, **kw):
        return self._store(key, value if value is not None else min_value, label)

    def toggle(self, label, value=False, key=None, **kw):
        return self._store(key, value, label)

    checkbox = toggle

    def button(self, label, key=None, on_click=None, args=(), kwargs=None, **kw):
        k = key or label
        if k in REC.clicks:
            REC.clicks.discard(k)
            if on_click:
                on_click(*args, **(kwargs or {}))
            return True
        return False

    def download_button(self, label, data, file_name=None, mime=None, key=None, **kw):
        REC.downloads.append({"label": label, "data": data, "file_name": file_name, "mime": mime})
        return False


def _cache(func=None, **kw):
    if func is not None and callable(func):
        return func
    return lambda f: f


def install():
    existing = sys.modules.get("streamlit")
    if existing is not None and getattr(existing, "__zilal_stub__", False):
        return existing  # نسخة واحدة مشتركة بين كل ملفات الاختبار
    st = types.ModuleType("streamlit")
    st.__zilal_stub__ = True
    st.__version__ = "1.50.0"
    st.session_state = SessionState()
    st.query_params = {}
    main = Container(st)
    for name in dir(Container):
        if not name.startswith("_"):
            setattr(st, name, getattr(main, name))
    st.sidebar = Container(st)
    st.cache_data = _cache
    st.cache_resource = _cache
    st.set_page_config = lambda **kw: None

    def stop():
        raise StopApp()
    st.stop = stop
    st.rerun = lambda: None
    comps = types.ModuleType("streamlit.components")
    v1 = types.ModuleType("streamlit.components.v1")
    v1.html = lambda html, height=None, scrolling=False, **kw: REC.components.append({"html": html, "height": height})
    comps.v1 = v1
    st.components = comps
    sys.modules["streamlit"] = st
    sys.modules["streamlit.components"] = comps
    sys.modules["streamlit.components.v1"] = v1
    return st
