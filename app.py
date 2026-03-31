import streamlit as st
from openai import OpenAI
import os
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

# ── Fetch live USD/INR rate ────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_usd_inr():
    try:
        ticker = yf.Ticker("USDINR=X")
        data = ticker.fast_info
        return float(data["last_price"])
    except:
        try:
            r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
            return r.json()["rates"]["INR"]
        except:
            return 83.5

# ── Fetch live gold price ──────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_live_gold_inr():
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
        d = r.json()
        usd_price = d.get("price", 0)
        change_usd = d.get("ch", 0)
        change_pct = d.get("chp", 0)
        inr_rate = get_usd_inr()
        troy_to_gram = 31.1035
        price_per_gram = (usd_price / troy_to_gram) * inr_rate
        change_per_gram = (change_usd / troy_to_gram) * inr_rate
        return {
            "per_gram": price_per_gram,
            "per_10g": price_per_gram * 10,
            "change_per_gram": change_per_gram,
            "change_pct": change_pct,
            "inr_rate": inr_rate,
            "timestamp": d.get("updatedAt", "")
        }
    except Exception as e:
        return None

# ── Fetch historical gold data in INR ─────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_historical_inr(period="1mo", interval="1d"):
    try:
        gold = yf.download("GC=F", period=period, interval=interval, progress=False)
        fx   = yf.download("USDINR=X", period=period, interval=interval, progress=False)

        gold_close = gold["Close"].squeeze()
        fx_close   = fx["Close"].squeeze()

        fx_close   = fx_close.reindex(gold_close.index, method="ffill")
        inr_series = (gold_close / 31.1035) * fx_close
        inr_series = inr_series.dropna()
        inr_series.name = "₹ per gram (24K)"
        return inr_series
    except Exception as e:
        return None

# ── Compute change vs N days ago ──────────────────────────────────────────────
def compute_change(series, current_price):
    if series is None or len(series) < 2:
        return None, None
    old_price = float(series.iloc[0])
    change    = current_price - old_price
    pct       = (change / old_price) * 100
    return change, pct

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gold Assist 🇮🇳", page_icon="💰", layout="wide")
st.title("💰 Gold Assist")
st.caption("Live 24K gold prices for Indian investors • Powered by gold-api.com + yfinance")

# ── Fetch live data ────────────────────────────────────────────────────────────
gold = get_live_gold_inr()

if gold:
    per_gram    = gold["per_gram"]
    per_10g     = gold["per_10g"]
    change_gram = gold["change_per_gram"]
    change_pct  = gold["change_pct"]
    ts          = gold["timestamp"][:16] if gold["timestamp"] else "Live"

    # ── Hero price ─────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style='padding: 1.2rem 0 0.5rem 0'>
        <span style='font-size: 2.8rem; font-weight: 700; color: var(--color-text-primary)'>
            ₹{per_gram:,.0f}
        </span>
        <span style='font-size: 1.1rem; color: var(--color-text-secondary); margin-left: 10px'>
            per gram · 24K · Last updated {ts}
        </span>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Per Gram (24K)",   f"₹{per_gram:,.0f}",  f"₹{change_gram:+.0f} today")
    col2.metric("Per 10 Grams",     f"₹{per_10g:,.0f}",   f"{change_pct:+.2f}% today")
    col3.metric("USD/INR Rate",     f"₹{gold['inr_rate']:.2f}")
    col4.metric("Data source",      "gold-api.com", "Free & unlimited")
else:
    st.error("Could not fetch live gold price. Please refresh.")
    per_gram = 0

st.divider()

# ── Period buttons ─────────────────────────────────────────────────────────────
st.subheader("📈 Price History (24K Gold · ₹/gram)")

PERIODS = {
    "1D":  ("1d",  "5m"),
    "1W":  ("5d",  "1h"),
    "1M":  ("1mo", "1d"),
    "3M":  ("3mo", "1d"),
    "1Y":  ("1y",  "1wk"),
    "5Y":  ("5y",  "1mo"),
}

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

selected         = st.session_state.chart_period
period, interval = PERIODS[selected]

with st.spinner(f"Loading {selected} data..."):
    hist = get_historical_inr(period, interval)

if hist is not None and len(hist) > 1:
    df_chart = hist.reset_index()
    df_chart.columns = ["Date", "₹ per gram (24K)"]
    df_chart["Date"] = pd.to_datetime(df_chart["Date"])

    # Area chart via Altair
    import altair as alt
    base = alt.Chart(df_chart).mark_area(
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
        x=alt.X("Date:T", axis=alt.Axis(format="%d %b %y", labelAngle=-30, title="")),
        y=alt.Y("₹ per gram (24K):Q",
                scale=alt.Scale(zero=False),
                axis=alt.Axis(title="₹ per gram", format=",.0f")),
        tooltip=[
            alt.Tooltip("Date:T", format="%d %b %Y"),
            alt.Tooltip("₹ per gram (24K):Q", format=",.0f", title="₹/gram")
        ]
    ).properties(height=360)

    st.altair_chart(base, use_container_width=True)

    # Change stats for selected period
    change_val, change_pct_period = compute_change(hist, per_gram)
    if change_val is not None:
        direction = "🟢" if change_val >= 0 else "🔴"
        st.markdown(
            f"{direction} **{selected} change:** "
            f"₹{change_val:+,.0f}/gram &nbsp;|&nbsp; **{change_pct_period:+.2f}%**"
        )
else:
    st.info("Historical data temporarily unavailable for this period.")

st.divider()

# ── Change summary table ───────────────────────────────────────────────────────
st.subheader("📊 Change Summary")

summary_data = []
summary_periods = [
    ("1 Day",   "2d",  "1h"),
    ("1 Week",  "5d",  "1h"),
    ("1 Month", "1mo", "1d"),
    ("3 Months","3mo", "1d"),
    ("1 Year",  "1y",  "1wk"),
]

for label, p, iv in summary_periods:
    data = get_historical_inr(p, iv)
    if data is not None and len(data) > 1:
        chg, pct = compute_change(data, per_gram)
        if chg is not None:
            arrow = "▲" if chg >= 0 else "▼"
            summary_data.append({
                "Period":      label,
                "Change (₹/g)": f"{arrow} ₹{abs(chg):,.0f}",
                "Change (%)":   f"{arrow} {abs(pct):.2f}%",
                "Trend":        "🟢 Up" if chg >= 0 else "🔴 Down"
            })

if summary_data:
    st.dataframe(
        pd.DataFrame(summary_data),
        hide_index=True,
        use_container_width=True
    )

st.divider()

# ── AI Chat ────────────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "system",
            "content": (
                "You are an expert financial assistant for Indian gold investors. "
                "You receive live 24K gold prices in INR. "
                "Give practical advice on physical gold, Sovereign Gold Bonds (SGBs — 2.5% annual interest), "
                "Gold ETFs, digital gold, and jewellery. "
                "Factor in Indian taxes: LTCG (>3 years = 20% with indexation), "
                "STT on ETFs, and 3% GST on physical gold. "
                "Be concise and data-driven. Remind users this is not SEBI-registered advice."
            )
        }
    ]

for msg in st.session_state.messages[1:]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

question = st.chat_input("Ask about gold investment... e.g. 'Should I buy SGBs or Gold ETFs?'")

if question:
    # build summary for AI context
    change_lines = "\n".join(
        f"  - {row['Period']}: {row['Change (₹/g)']} ({row['Change (%)']})"
        for row in summary_data
    ) if summary_data else "  - Historical data unavailable"

    context = f"""[Live Market Data — INR]
- 24K gold: ₹{per_gram:,.0f}/gram | ₹{per_gram*10:,.0f}/10g
- Today's change: ₹{change_gram:+.0f}/gram ({change_pct:+.2f}%)
- USD/INR: ₹{gold['inr_rate']:.2f}
- Period changes:
{change_lines}
"""
    full_message = f"{context}\nUser question: {question}"
    st.session_state.messages.append({"role": "user", "content": full_message})

    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing..."):
            try:
                response = client.chat.completions.create(
                    model="openrouter/free",
                    messages=st.session_state.messages,
                    max_tokens=800
                )
                answer = response.choices[0].message.content
                st.write(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                st.error(f"AI Error: {str(e)}")

st.divider()
st.caption("⚠️ Not SEBI-registered financial advice. Prices exclude GST & making charges. Consult a registered advisor before investing.")