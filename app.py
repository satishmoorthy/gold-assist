import streamlit as st
from openai import OpenAI
import os
import pyotp
import pandas as pd
import altair as alt
from smartapi import SmartConnect
from dotenv import load_dotenv

load_dotenv()

# ── Angel One credentials ──────────────────────────────────────────────────────
API_KEY      = os.getenv("ANGELONE_API_KEY")
CLIENT_ID    = os.getenv("ANGELONE_CLIENT_ID")
MPIN         = os.getenv("ANGELONE_MPIN")
TOTP_SECRET  = os.getenv("ANGELONE_TOTP_SECRET")

# ── OpenRouter AI client ───────────────────────────────────────────────────────
ai_client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

# ── Angel One login ────────────────────────────────────────────────────────────
@st.cache_resource(ttl=3600)  # re-login every hour
def get_angel_session():
    try:
        obj   = SmartConnect(api_key=API_KEY)
        totp  = pyotp.TOTP(TOTP_SECRET).now()
        data  = obj.generateSession(CLIENT_ID, MPIN, totp)
        if data["status"]:
            return obj
        else:
            st.error(f"Angel One login failed: {data['message']}")
            return None
    except Exception as e:
        st.error(f"Angel One connection error: {str(e)}")
        return None

# ── Fetch live MCX Gold price ──────────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_live_gold_mcx():
    try:
        obj = get_angel_session()
        if not obj:
            return None

        # MCX Gold 1kg contract token
        # symboltoken for GOLD on MCX
        ltp_data = obj.ltpData("MCX", "GOLD", "234230")
        if ltp_data["status"]:
            d         = ltp_data["data"]
            ltp       = float(d["ltp"])          # ₹ per 10g on MCX
            per_gram  = ltp / 10                 # convert to per gram
            close     = float(d.get("close", ltp))
            change    = ltp - close
            change_pct = (change / close) * 100 if close else 0
            return {
                "per_gram":   per_gram,
                "per_10g":    ltp,
                "change":     change / 10,
                "change_pct": change_pct,
                "high":       float(d.get("high", 0)) / 10,
                "low":        float(d.get("low",  0)) / 10,
                "open":       float(d.get("open", 0)) / 10,
            }
    except Exception as e:
        st.warning(f"MCX data error: {str(e)}")
        return None

# ── Fetch historical candle data ───────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_historical(period="1M"):
    try:
        obj = get_angel_session()
        if not obj:
            return None

        from datetime import datetime, timedelta
        now = datetime.now()

        period_map = {
            "1D": (now - timedelta(days=1),   "FIVE_MINUTE"),
            "1W": (now - timedelta(weeks=1),  "ONE_HOUR"),
            "1M": (now - timedelta(days=30),  "ONE_DAY"),
            "3M": (now - timedelta(days=90),  "ONE_DAY"),
            "1Y": (now - timedelta(days=365), "ONE_WEEK"),
            "5Y": (now - timedelta(days=1825),"ONE_MONTH"),
        }

        from_dt, resolution = period_map[period]

        params = {
            "exchange":    "MCX",
            "symboltoken": "234230",
            "interval":    resolution,
            "fromdate":    from_dt.strftime("%Y-%m-%d %H:%M"),
            "todate":      now.strftime("%Y-%m-%d %H:%M"),
        }

        resp = obj.getCandleData(params)
        if resp["status"] and resp["data"]:
            rows = []
            for candle in resp["data"]:
                # candle = [timestamp, open, high, low, close, volume]
                rows.append({
                    "Date":          pd.to_datetime(candle[0]),
                    "₹ per gram":    float(candle[4]) / 10,  # close / 10
                })
            df = pd.DataFrame(rows).set_index("Date")
            return df["₹ per gram"]
        return None
    except Exception as e:
        st.warning(f"Historical data error: {str(e)}")
        return None

# ── Change helper ──────────────────────────────────────────────────────────────
def compute_change(series, current):
    if series is None or len(series) < 2:
        return None, None
    old = float(series.iloc[0])
    chg = current - old
    pct = (chg / old) * 100
    return chg, pct

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gold Assist 🇮🇳",
                   page_icon="💰", layout="wide")
st.title("💰 Gold Assist")
st.caption("Live MCX gold prices for Indian investors • Powered by Angel One SmartAPI")

# ── Live price ─────────────────────────────────────────────────────────────────
gold = get_live_gold_mcx()

if gold:
    per_gram   = gold["per_gram"]
    per_10g    = gold["per_10g"]
    change     = gold["change"]
    change_pct = gold["change_pct"]

    st.markdown(f"""
    <div style='padding:1.2rem 0 0.5rem 0'>
        <span style='font-size:2.8rem;font-weight:700;
                     color:var(--color-text-primary)'>
            ₹{per_gram:,.0f}
        </span>
        <span style='font-size:1.1rem;
                     color:var(--color-text-secondary);
                     margin-left:10px'>
            per gram · 24K · MCX Live
        </span>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💛 Per Gram (24K)",
                f"₹{per_gram:,.0f}",
                f"₹{change:+.0f} ({change_pct:+.2f}%) today")
    col2.metric("💛 Per 10 Grams",
                f"₹{per_10g:,.0f}")
    col3.metric("📈 Day High",
                f"₹{gold['high']:,.0f}")
    col4.metric("📉 Day Low",
                f"₹{gold['low']:,.0f}")

    st.caption("ℹ️ MCX Gold (1kg contract) · Direct INR · "
               "Jeweller rates include 3% GST + making charges.")
else:
    st.warning("⚠️ Could not fetch MCX price. "
               "Market may be closed or check your Angel One credentials.")
    per_gram = change = change_pct = 0

st.divider()

# ── Chart ──────────────────────────────────────────────────────────────────────
st.subheader("📈 Price History (24K Gold · ₹/gram · MCX)")

PERIODS = ["1D", "1W", "1M", "3M", "1Y", "5Y"]

if "chart_period" not in st.session_state:
    st.session_state.chart_period = "1M"

cols = st.columns(len(PERIODS))
for i, label in enumerate(PERIODS):
    if cols[i].button(
        label,
        use_container_width=True,
        type="primary" if st.session_state.chart_period == label else "secondary"
    ):
        st.session_state.chart_period = label

selected = st.session_state.chart_period

with st.spinner(f"Loading {selected} data..."):
    hist = get_historical(selected)

if hist is not None and len(hist) > 1:
    df_chart = hist.reset_index()
    df_chart.columns = ["Date", "₹ per gram (24K)"]

    chart = alt.Chart(df_chart).mark_area(
        line={"color": "#F4A623", "strokeWidth": 2},
        color=alt.Gradient(
            gradient="linear",
            stops=[
                alt.GradientStop(color="#F4A623", offset=0),
                alt.GradientStop(color="rgba(244,166,35,0.05)", offset=1),
            ],
            x1=0, x2=0, y1=0, y2=1,
        )
    ).encode(
        x=alt.X("Date:T",
                axis=alt.Axis(format="%d %b %y",
                              labelAngle=-30, title="")),
        y=alt.Y("₹ per gram (24K):Q",
                scale=alt.Scale(zero=False),
                axis=alt.Axis(title="₹ per gram",
                              format=",.0f")),
        tooltip=[
            alt.Tooltip("Date:T", format="%d %b %Y"),
            alt.Tooltip("₹ per gram (24K):Q",
                        format=",.0f", title="₹/gram")
        ]
    ).properties(height=380)

    st.altair_chart(chart, use_container_width=True)

    chg_val, chg_pct = compute_change(hist, per_gram)
    if chg_val is not None:
        icon = "🟢" if chg_val >= 0 else "🔴"
        st.markdown(
            f"{icon} **{selected} change:** "
            f"₹{chg_val:+,.0f}/gram &nbsp;|&nbsp; "
            f"**{chg_pct:+.2f}%**"
        )
else:
    st.info("Historical data unavailable. MCX may be closed right now.")

st.divider()

# ── Change summary ─────────────────────────────────────────────────────────────
st.subheader("📊 Change Summary")

SUMMARY = [
    ("1 Day",    "1D"),
    ("1 Week",   "1W"),
    ("1 Month",  "1M"),
    ("3 Months", "3M"),
    ("1 Year",   "1Y"),
]

rows = []
for label, p in SUMMARY:
    data = get_historical(p)
    if data is not None and len(data) > 1:
        chg, pct = compute_change(data, per_gram)
        if chg is not None:
            arrow = "▲" if chg >= 0 else "▼"
            rows.append({
                "Period":       label,
                "Change (₹/g)": f"{arrow} ₹{abs(chg):,.0f}",
                "Change (%)":   f"{arrow} {abs(pct):.2f}%",
                "Trend":        "🟢 Up" if chg >= 0 else "🔴 Down"
            })

if rows:
    st.dataframe(pd.DataFrame(rows),
                 hide_index=True,
                 use_container_width=True)
else:
    st.info("Summary unavailable. MCX may be closed.")

st.divider()

# ── AI Chat ────────────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "system",
            "content": (
                "You are an expert financial assistant for Indian gold investors. "
                "You receive live 24K MCX gold prices in INR via Angel One SmartAPI. "
                "Give practical advice on: physical gold (coins/bars), "
                "Sovereign Gold Bonds (SGBs — 2.5% annual interest, tax-free on maturity), "
                "Gold ETFs (GOLDBEES, SBI Gold), digital gold, and jewellery. "
                "Factor in Indian taxes: LTCG 12.5% without indexation (post-2024 budget), "
                "3% GST on physical gold, STT on ETFs. "
                "Be concise and data-driven. "
                "Always remind users this is not SEBI-registered financial advice."
            )
        }
    ]

for msg in st.session_state.messages[1:]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

question = st.chat_input(
    "Ask about gold investment... e.g. 'Should I buy SGBs or Gold ETFs?'"
)

if question:
    summary_lines = "\n".join(
        f"  - {r['Period']}: {r['Change (₹/g)']} ({r['Change (%)']})"
        for r in rows
    ) if rows else "  - Unavailable"

    context = f"""[Live MCX Market Data · INR · Angel One SmartAPI]
- 24K gold: ₹{per_gram:,.0f}/gram | ₹{per_10g:,.0f}/10g
- Today's change: ₹{change:+.0f}/gram ({change_pct:+.2f}%)
- Day High: ₹{gold['high']:,.0f} | Day Low: ₹{gold['low']:,.0f}
- Period changes:
{summary_lines}
""" if gold else "[Live data unavailable]"

    full_msg = f"{context}\nUser question: {question}"
    st.session_state.messages.append({"role": "user",
                                       "content": full_msg})

    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing..."):
            try:
                response = ai_client.chat.completions.create(
                    model="openrouter/free",
                    messages=st.session_state.messages,
                    max_tokens=800
                )
                answer = response.choices[0].message.content
                st.write(answer)
                st.session_state.messages.append(
                    {"role": "assistant", "content": answer}
                )
            except Exception as e:
                st.error(f"AI Error: {str(e)}")

st.divider()
st.caption(
    "⚠️ Not SEBI-registered financial advice. "
    "Live MCX gold prices via Angel One SmartAPI. "
    "Jeweller rates include GST & making charges. "
    "Consult a registered advisor before investing."
)