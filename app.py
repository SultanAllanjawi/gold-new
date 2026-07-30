"""
THESIS: مرصد عملي يشبه سجل فحص السبائك؛ يرفض لوحة البطاقات العامة ويجعل مصدر الرقم وحالته جزءًا من الرقم نفسه.
OWN-WORLD: ورق فحوص رمادي فاتح، حبر فحمي، ذهب مختوم، وأخضر زمردي للحالة السليمة؛ صفوف قياس وحدود دقيقة.
STORY: يرى المستخدم صلاحية السعر أولًا، ثم يحسب صفقة، ويسجلها، ويراقب نتيجتها وتنبيهاته.
FIRST VIEWPORT: شريط مصدر واضح، عنوان موجز، سعران كبيران للذهب والفضة، ثم جدول العيارات بلا تمرير أفقي.
FORM: «دفتر فحص وسجل سبائك»، السادسة في قائمة الاتجاهات المحلية؛ staging سجل مستمر للأحداث؛ seed 8cdb9acd.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / ".gold_observatory"
DB_PATH = DATA_DIR / "observatory.db"
CACHE_PATH = DATA_DIR / "last_prices.json"
API_URL = "https://api.metals.dev/v1/latest"
KARATS = {24: 1.0, 22: 22 / 24, 21: 21 / 24, 18: 18 / 24}


st.set_page_config(
    page_title="مرصد الذهب والفضة",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def money(value: float) -> str:
    return f"{value:,.2f} د.إ"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ensure_storage() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                metal TEXT NOT NULL,
                karat INTEGER NOT NULL,
                weight_g REAL NOT NULL CHECK(weight_g > 0),
                paid_total REAL NOT NULL CHECK(paid_total >= 0),
                note TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                metal TEXT NOT NULL,
                target REAL NOT NULL CHECK(target > 0),
                direction TEXT NOT NULL CHECK(direction IN ('above', 'below')),
                enabled INTEGER NOT NULL DEFAULT 1
            );
            """
        )


@contextmanager
def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def secret_api_key() -> str:
    try:
        return str(st.secrets.get("METALS_DEV_API_KEY", "")).strip()
    except Exception:
        return ""


def valid_payload(payload: dict[str, Any]) -> bool:
    return (
        payload.get("status") == "success"
        and payload.get("currency") == "AED"
        and payload.get("unit") == "g"
        and float(payload.get("metals", {}).get("gold", 0)) > 0
        and float(payload.get("metals", {}).get("silver", 0)) > 0
    )


def save_cache(payload: dict[str, Any]) -> None:
    cache = {
        "gold": float(payload["metals"]["gold"]),
        "silver": float(payload["metals"]["silver"]),
        "source_timestamp": payload.get("timestamp", now_iso()),
        "saved_at": now_iso(),
        "currency": "AED",
        "unit": "g",
    }
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def load_cache() -> dict[str, Any] | None:
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if float(data["gold"]) > 0 and float(data["silver"]) > 0:
            return data
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def fetch_prices(api_key: str) -> tuple[dict[str, Any] | None, str | None]:
    if not api_key:
        return None, "لم تتم إضافة مفتاح Metals.Dev بعد."
    try:
        response = requests.get(
            API_URL,
            params={"api_key": api_key, "currency": "AED", "unit": "g"},
            headers={"Accept": "application/json", "User-Agent": "GoldObservatory/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if not valid_payload(payload):
            message = payload.get("message") or "استجابة غير متوقعة من مزود الأسعار."
            return None, str(message)
        save_cache(payload)
        return load_cache(), None
    except (requests.RequestException, ValueError) as exc:
        return None, f"تعذر الاتصال بالمصدر: {exc.__class__.__name__}"


def get_prices(refresh: bool = False) -> tuple[dict[str, Any] | None, str, str | None]:
    if "prices" not in st.session_state or refresh:
        fresh, error = fetch_prices(secret_api_key())
        cached = load_cache()
        if fresh:
            st.session_state.prices = fresh
            st.session_state.price_state = ("live", None)
        elif cached:
            st.session_state.prices = cached
            st.session_state.price_state = ("cached", error)
        else:
            st.session_state.prices = None
            st.session_state.price_state = ("missing", error)
    status, error = st.session_state.price_state
    return st.session_state.prices, status, error


def current_value(metal: str, karat: int, weight: float, prices: dict[str, Any]) -> float:
    base = float(prices[metal])
    purity = KARATS.get(karat, 1.0) if metal == "gold" else 1.0
    return base * purity * weight


def fmt_timestamp(value: str) -> str:
    try:
        dt = parse_time(value).astimezone()
        return dt.strftime("%Y/%m/%d، %H:%M")
    except (ValueError, TypeError):
        return "غير معروف"


def inject_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Kufi+Arabic:wght@400;500;600;700&display=swap');
        :root {
            --ink: #171713; --muted: #68675f; --paper: #f4f3ed;
            --line: #d8d5c8; --gold: #b78922; --green: #116149; --red: #a3392e;
        }
        html, body, [class*="css"], [data-testid="stAppViewContainer"] {
            font-family: "Noto Kufi Arabic", "Segoe UI", sans-serif;
        }
        [data-testid="stAppViewContainer"] {
            direction: rtl; color: var(--ink);
            background:
              linear-gradient(rgba(23,23,19,.025) 1px, transparent 1px) 0 0/100% 32px,
              var(--paper);
        }
        [data-testid="stHeader"] { background: rgba(244,243,237,.94); }
        [data-testid="stMainBlockContainer"] { max-width: 1180px; padding-top: 1.6rem; }
        .masthead { display:flex; justify-content:space-between; align-items:end; gap:1rem; border-bottom:2px solid var(--ink); padding:1rem 0 .85rem; margin-bottom:1rem; }
        .brand { font-size:clamp(1.45rem,4vw,2.5rem); font-weight:700; letter-spacing:-.03em; margin:0; }
        .edition { color:var(--muted); font-size:.78rem; white-space:nowrap; }
        .source-strip { display:flex; gap:.7rem; align-items:center; flex-wrap:wrap; padding:.65rem .8rem; border:1px solid var(--line); background:#fff; font-size:.78rem; }
        .dot { width:.62rem; height:.62rem; border-radius:50%; display:inline-block; background:var(--green); }
        .dot.cached { background:var(--gold); } .dot.missing { background:var(--red); }
        .quote-grid { display:grid; grid-template-columns:1.35fr 1fr; gap:1px; background:var(--ink); margin:1rem 0; border:1px solid var(--ink); }
        .quote { background:#fff; padding:clamp(1rem,4vw,2.2rem); position:relative; overflow:hidden; }
        .quote.gold { background:#d4ad4b; }
        .quote-name { font-size:.82rem; font-weight:700; }
        .quote-value { font-size:clamp(2rem,7vw,4.8rem); line-height:1.05; font-weight:700; direction:rtl; margin:.5rem 0; letter-spacing:-.04em; }
        .quote-unit { color:#4c493f; font-size:.75rem; }
        .assay-table { display:grid; grid-template-columns:repeat(4,1fr); border-top:1px solid var(--ink); border-bottom:1px solid var(--ink); margin:1.5rem 0 2.3rem; }
        .assay-cell { padding:1rem; border-left:1px solid var(--line); }
        .assay-cell:last-child { border-left:0; }
        .assay-k { font-size:.74rem;color:var(--muted); }
        .assay-v { font-size:1.25rem;font-weight:700; direction:rtl; }
        .section-title { font-size:1.35rem; font-weight:700; margin:2.2rem 0 .2rem; }
        .section-note { color:var(--muted); font-size:.78rem; margin-bottom:1rem; }
        .result-band { background:var(--ink); color:#fff; padding:1.15rem 1.3rem; margin:1rem 0; display:flex; align-items:baseline; justify-content:space-between; gap:1rem; }
        .result-band strong { color:#f0c85c; font-size:1.55rem; }
        .legal { border-top:1px solid var(--line); margin-top:2.5rem; padding:1rem 0 2rem; color:var(--muted); font-size:.72rem; line-height:1.8; }
        div[data-testid="stMetric"] { background:transparent; border-top:1px solid var(--ink); padding:.8rem 0; }
        div[data-testid="stForm"] { border:1px solid var(--line); border-radius:0; background:#fff; }
        div[data-testid="stForm"] label,
        div[data-testid="stForm"] p,
        div[data-testid="stForm"] span,
        div[data-testid="stForm"] input,
        div[data-testid="stForm"] [data-baseweb="select"] * { color:var(--ink) !important; }
        .stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {
            border-radius:0 !important; min-height:44px; font-weight:700;
            background:var(--ink) !important; color:#fff !important; border:1px solid var(--ink) !important;
        }
        .stButton button *, .stDownloadButton button *, [data-testid="stFormSubmitButton"] button * {
            color:inherit !important;
        }
        div[data-testid="stForm"] [data-testid="stFormSubmitButton"] button,
        div[data-testid="stForm"] [data-testid="stFormSubmitButton"] button * {
            color:#fff !important;
        }
        .stButton button[kind="primary"] {
            background:var(--gold) !important; color:var(--ink) !important; border-color:var(--ink) !important;
        }
        .stButton button:hover, [data-testid="stFormSubmitButton"] button:hover {
            background:var(--ink) !important; color:#fff !important;
        }
        .stButton button:focus-visible, [data-testid="stFormSubmitButton"] button:focus-visible {
            outline:3px solid var(--gold) !important; outline-offset:2px;
        }
        .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
            border-radius:0 !important; background:#fff !important; color:var(--ink) !important;
        }
        [data-testid="stAlert"] { color:var(--ink) !important; }
        [data-testid="stAlert"] * { color:inherit !important; }
        [data-testid="stTabs"] [data-baseweb="tab-list"] { gap:0; border-bottom:1px solid var(--ink); }
        [data-testid="stTabs"] button { border-radius:0; padding:.8rem 1.1rem; color:var(--muted) !important; }
        [data-testid="stTabs"] button[aria-selected="true"] { color:var(--ink) !important; font-weight:700; }
        [data-testid="stTabs"] [data-baseweb="tab-highlight"] { background:var(--gold) !important; }
        .chart-note { display:flex; justify-content:space-between; gap:1rem; flex-wrap:wrap; color:var(--muted); font-size:.75rem; margin:.45rem 0 1rem; }
        .storage-note { padding:.9rem 1rem; background:#fff; border:1px solid var(--gold); color:var(--ink); margin:1rem 0; font-size:.82rem; }
        @media (max-width: 700px) {
          [data-testid="stMainBlockContainer"] { padding-left:1rem; padding-right:1rem; }
          .masthead { align-items:start; flex-direction:column; }
          .quote-grid { grid-template-columns:1fr; }
          .assay-table { grid-template-columns:repeat(2,1fr); }
          .assay-cell:nth-child(2) { border-left:0; }
          .assay-cell:nth-child(-n+2) { border-bottom:1px solid var(--line); }
          .result-band { align-items:start; flex-direction:column; }
        }
        @media (prefers-reduced-motion: reduce) { * { scroll-behavior:auto !important; transition:none !important; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_strip(prices: dict[str, Any] | None, status: str, error: str | None) -> None:
    labels = {"live": "متصل — قراءة حديثة", "cached": "دون اتصال — آخر قراءة محفوظة", "missing": "بانتظار إعداد مصدر السعر"}
    stamp = fmt_timestamp(prices["source_timestamp"]) if prices else "لا توجد قراءة"
    detail = f" · {error}" if error and status != "live" else ""
    st.markdown(
        f'<div class="source-strip"><span class="dot {status}"></span>'
        f'<strong>{labels[status]}</strong><span>Metals.Dev · {stamp}{detail}</span></div>',
        unsafe_allow_html=True,
    )


def overview(prices: dict[str, Any] | None) -> None:
    if not prices:
        st.warning("أضف مفتاح API في ‎.streamlit/secrets.toml ثم اضغط «تحديث السعر». لن نعرض أرقامًا افتراضية على أنها حقيقية.")
        st.code('METALS_DEV_API_KEY = "your_key_here"', language="toml")
        return
    gold = float(prices["gold"])
    silver = float(prices["silver"])
    st.markdown(
        f"""
        <div class="quote-grid">
          <div class="quote gold"><div class="quote-name">ذهب خام · 24 قيراط</div>
            <div class="quote-value">{gold:,.2f}</div><div class="quote-unit">درهم إماراتي / جرام</div></div>
          <div class="quote"><div class="quote-name">فضة خام · نقاء 999</div>
            <div class="quote-value">{silver:,.2f}</div><div class="quote-unit">درهم إماراتي / جرام</div></div>
        </div>
        <div class="assay-table">
          {''.join(f'<div class="assay-cell"><div class="assay-k">ذهب عيار {k}</div><div class="assay-v">{gold*p:,.2f} د.إ</div></div>' for k,p in KARATS.items())}
        </div>
        """,
        unsafe_allow_html=True,
    )


def tradingview_chart() -> None:
    st.markdown(
        '<div class="section-title">الرسم العالمي للذهب</div>'
        '<div class="section-note">ذهب فوري مقابل الدولار الأمريكي (XAU/USD) من TradingView. '
        'هذا الرسم بوحدة الدولار/الأونصة ويختلف عن بطاقات الدرهم/الجرام أعلاه.</div>',
        unsafe_allow_html=True,
    )
    components.html(
        """
        <div class="tradingview-widget-container" style="height:680px;width:100%">
          <div class="tradingview-widget-container__widget" style="height:calc(100% - 32px);width:100%"></div>
          <div class="tradingview-widget-copyright">
            <a href="https://www.tradingview.com/symbols/XAUUSD/" rel="noopener nofollow" target="_blank">
              <span class="blue-text">Gold Spot / U.S. Dollar chart</span>
            </a> by TradingView
          </div>
          <script type="text/javascript"
            src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
          {
            "autosize": true,
            "symbol": "OANDA:XAUUSD",
            "interval": "D",
            "timezone": "Asia/Dubai",
            "theme": "light",
            "backgroundColor": "#f4f3ed",
            "gridColor": "rgba(23,23,19,0.08)",
            "style": "1",
            "locale": "en",
            "allow_symbol_change": false,
            "hide_side_toolbar": true,
            "withdateranges": true,
            "save_image": false,
            "calendar": false,
            "support_host": "https://www.tradingview.com"
          }
          </script>
        </div>
        """,
        height=710,
        scrolling=False,
    )
    st.markdown(
        '<div class="chart-note"><span>المصدر: TradingView · الرمز: OANDA:XAUUSD</span>'
        '<span>الرسم مرجعي مستقل عن سعر Metals.Dev المعروض أعلى الصفحة.</span></div>',
        unsafe_allow_html=True,
    )


def calculator(prices: dict[str, Any] | None) -> None:
    st.markdown('<div class="section-title">حاسبة الشراء</div><div class="section-note">تفصل قيمة الخام عن المصنعية والضريبة حتى تبقى النتيجة قابلة للمراجعة.</div>', unsafe_allow_html=True)
    if not prices:
        st.info("تحتاج الحاسبة إلى قراءة سعر محفوظة أو اتصال بالمصدر.")
        return
    with st.form("calculator"):
        c1, c2, c3 = st.columns(3)
        metal_label = c1.selectbox("المعدن", ["ذهب", "فضة"])
        metal = "gold" if metal_label == "ذهب" else "silver"
        karat = c2.selectbox("العيار", [24, 22, 21, 18], disabled=metal == "silver")
        weight = c3.number_input("الوزن (جرام)", min_value=0.01, value=10.0, step=0.1)
        c4, c5, c6 = st.columns(3)
        workmanship = c4.number_input("المصنعية / جرام", min_value=0.0, value=0.0, step=1.0)
        other = c5.number_input("رسوم أخرى", min_value=0.0, value=0.0, step=1.0)
        vat = c6.number_input("الضريبة (%)", min_value=0.0, value=5.0, step=0.5)
        submitted = st.form_submit_button("احسب التكلفة", use_container_width=True)
    if submitted:
        raw = current_value(metal, int(karat), weight, prices)
        before_tax = raw + workmanship * weight + other
        total = before_tax * (1 + vat / 100)
        st.markdown(f'<div class="result-band"><span>التكلفة التقديرية الكاملة</span><strong>{money(total)}</strong></div>', unsafe_allow_html=True)
        st.caption(f"خام {money(raw)} · مصنعية {money(workmanship * weight)} · رسوم {money(other)} · ضريبة {money(total-before_tax)}")


def purchases(prices: dict[str, Any] | None) -> None:
    st.markdown('<div class="section-title">سجل المشتريات</div><div class="section-note">الربح والخسارة مقارنة بقيمة الخام الحالية فقط.</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="storage-note"><strong>تنبيه التخزين السحابي:</strong> على Streamlit Community Cloud '
        'هذه البيانات مؤقتة وقد تختفي عند إعادة تشغيل الخادم. يلزم ربط قاعدة بيانات سحابية وحساب مستخدم للحفظ الدائم.</div>',
        unsafe_allow_html=True,
    )
    with st.form("purchase"):
        c1, c2, c3 = st.columns(3)
        metal_label = c1.selectbox("المعدن", ["ذهب", "فضة"], key="p_metal")
        metal = "gold" if metal_label == "ذهب" else "silver"
        karat = c2.selectbox("العيار", [24, 22, 21, 18], key="p_karat", disabled=metal == "silver")
        weight = c3.number_input("الوزن (جرام)", min_value=0.01, value=10.0, step=0.1, key="p_weight")
        c4, c5 = st.columns([1, 2])
        paid = c4.number_input("إجمالي المبلغ المدفوع", min_value=0.0, value=0.0, step=10.0)
        note = c5.text_input("ملاحظة اختيارية", max_chars=80)
        add = st.form_submit_button("سجّل عملية الشراء", use_container_width=True)
    if add:
        with db() as conn:
            conn.execute(
                "INSERT INTO purchases(created_at, metal, karat, weight_g, paid_total, note) VALUES(?,?,?,?,?,?)",
                (now_iso(), metal, int(karat), float(weight), float(paid), note.strip()),
            )
        st.success("تم حفظ عملية الشراء على هذا الجهاز.")
        st.rerun()

    with db() as conn:
        rows = conn.execute("SELECT * FROM purchases ORDER BY id DESC").fetchall()
    if not rows:
        st.info("لا توجد مشتريات مسجلة بعد.")
        return
    records = []
    for row in rows:
        value = current_value(row["metal"], row["karat"], row["weight_g"], prices) if prices else None
        pnl = value - row["paid_total"] if value is not None else None
        records.append(
            {
                "الرقم": row["id"],
                "التاريخ": fmt_timestamp(row["created_at"]),
                "المعدن": "ذهب" if row["metal"] == "gold" else "فضة",
                "العيار": row["karat"] if row["metal"] == "gold" else "999",
                "الوزن": f'{row["weight_g"]:,.2f} جم',
                "المدفوع": money(row["paid_total"]),
                "قيمة الخام الآن": money(value) if value is not None else "—",
                "الربح / الخسارة": money(pnl) if pnl is not None else "—",
                "ملاحظة": row["note"],
            }
        )
    st.dataframe(pd.DataFrame(records), hide_index=True, use_container_width=True)
    ids = [row["id"] for row in rows]
    c1, c2 = st.columns([3, 1])
    delete_id = c1.selectbox("حذف عملية", ids, format_func=lambda x: f"العملية #{x}")
    if c2.button("حذف المحدد", use_container_width=True):
        with db() as conn:
            conn.execute("DELETE FROM purchases WHERE id = ?", (delete_id,))
        st.rerun()


def alerts(prices: dict[str, Any] | None) -> None:
    st.markdown('<div class="section-title">تنبيهات السعر</div><div class="section-note">تظهر داخل التطبيق عند فتحه أو تحديث السعر؛ لا ترسل إشعار هاتف أو بريدًا.</div>', unsafe_allow_html=True)
    with st.form("alert"):
        c1, c2, c3 = st.columns(3)
        metal_label = c1.selectbox("المعدن", ["ذهب 24", "فضة 999"])
        metal = "gold" if metal_label.startswith("ذهب") else "silver"
        direction_label = c2.selectbox("نبهني عندما يصبح السعر", ["أعلى من أو يساوي", "أقل من أو يساوي"])
        direction = "above" if direction_label.startswith("أعلى") else "below"
        target = c3.number_input("السعر المستهدف / جرام", min_value=0.01, value=100.0, step=1.0)
        add = st.form_submit_button("أضف التنبيه", use_container_width=True)
    if add:
        with db() as conn:
            conn.execute(
                "INSERT INTO alerts(created_at, metal, target, direction) VALUES(?,?,?,?)",
                (now_iso(), metal, float(target), direction),
            )
        st.success("تم حفظ التنبيه.")
        st.rerun()
    with db() as conn:
        rows = conn.execute("SELECT * FROM alerts WHERE enabled = 1 ORDER BY id DESC").fetchall()
    if not rows:
        st.info("لا توجد تنبيهات نشطة.")
        return
    for row in rows:
        label = "ذهب 24" if row["metal"] == "gold" else "فضة 999"
        current = float(prices[row["metal"]]) if prices else None
        hit = current is not None and ((row["direction"] == "above" and current >= row["target"]) or (row["direction"] == "below" and current <= row["target"]))
        operator = "≥" if row["direction"] == "above" else "≤"
        message = f'#{row["id"]} · {label}: المستهدف {money(row["target"])} ({operator})'
        if hit:
            st.success(f"وصل السعر المستهدف — {message} · الحالي {money(current)}")
        else:
            st.write(message)
    ids = [row["id"] for row in rows]
    c1, c2 = st.columns([3, 1])
    delete_id = c1.selectbox("إزالة تنبيه", ids, format_func=lambda x: f"التنبيه #{x}")
    if c2.button("إزالة المحدد", use_container_width=True):
        with db() as conn:
            conn.execute("DELETE FROM alerts WHERE id = ?", (delete_id,))
        st.rerun()


def app() -> None:
    ensure_storage()
    inject_css()
    st.markdown(
        '<div class="masthead"><h1 class="brand">مرصد الذهب والفضة</h1>'
        '<span class="edition">الإمارات · أسعار الخام بالدرهم</span></div>',
        unsafe_allow_html=True,
    )
    refresh = st.button("تحديث السعر", type="primary")
    prices, status, error = get_prices(refresh=refresh)
    status_strip(prices, status, error)
    overview(prices)
    tab_chart, tab_calc, tab_purchases, tab_alerts, tab_about = st.tabs(
        ["الرسم البياني", "الحاسبة", "مشترياتي", "التنبيهات", "المصدر والخصوصية"]
    )
    with tab_chart:
        tradingview_chart()
    with tab_calc:
        calculator(prices)
    with tab_purchases:
        purchases(prices)
    with tab_alerts:
        alerts(prices)
    with tab_about:
        st.markdown('<div class="section-title">كيف تُحسب الأسعار؟</div>', unsafe_allow_html=True)
        st.write(
            "يطلب التطبيق سعر جرام الذهب والفضة بالدرهم مباشرة من Metals.Dev. "
            "أسعار العيارات = سعر ذهب 24 × (العيار ÷ 24). لا نضيف هامش متجر أو مصنعية إلا داخل الحاسبة."
        )
        st.markdown(
            "**دقة السعر:** القراءة هي سعر سوق فوري استرشادي من Metals.Dev، وليست سعر البيع النهائي في متجر ذهب. "
            "قد يتأخر المزود حتى نحو 60 ثانية، بينما يضيف المتجر المصنعية والهامش والضريبة."
        )
        st.markdown(
            "**التخزين:** عند التشغيل محليًا تُحفظ المشتريات والتنبيهات في `.gold_observatory`. "
            "على Streamlit Community Cloud أو Vercel لا يُعد هذا تخزينًا دائمًا؛ تحتاج قاعدة بيانات خارجية وحساب مستخدم."
        )
        st.markdown("**إعداد المصدر:** انسخ `.streamlit/secrets.toml.example` إلى `.streamlit/secrets.toml` وأضف مفتاحك.")
        if CACHE_PATH.exists():
            st.caption(f"ملف آخر قراءة: {CACHE_PATH}")
    st.markdown(
        '<div class="legal">الأسعار استرشادية للخام وقد تتأخر بحسب مزود البيانات. '
        'لا تشمل تلقائيًا المصنعية أو هامش المتجر أو الضريبة، وليست عرض بيع أو شراء ولا توصية استثمارية.</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    app()
