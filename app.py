import streamlit as st
from openai import OpenAI
import os
import requests
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

# ── Live gold price in INR (GOLDBEES = 1 unit ≈ 1 gram 24K gold) ──────────────
@st.cache_data(ttl=60)
def get_live_price_inr():
    try:
        ticker = yf.Ticker("GOLDBEES.NS")
        info = ticker.fast_info
        price = float(info["last_price"])
        prev  = float(info["previous_close"])
        change     = price - prev
        change_pct = (change / prev) * 100
        return {
            "per_gram":    price,
            "per_10g":     price * 10,
            "change":      change,
            "change_pct":  change_pct,
            "source":      "NSE: GOLDBEES"
        }
    except Exception as e:
        return None

# ── Historical data in INR ─────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_history(period="1mo", interval="1d"):
    try:
        df = yf.download("GOLDBEES.NS", period=period,
                         interval=interval, progress=False)
        series = df["Close"].squeeze().dropna()
        series.name = "₹ per gram (24K)"
        return series
    except:
        return None

# ── Change vs start of period ─────────────────────────────────────────────────
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
st.caption("Live 24K gold prices for Indian investors • NSE GOLDBEES (direct INR, no conversion)")

# ── Live price ─────────────────────────────────────────────────────────────────
gold = get_live_price_inr()

if gold:
    per_gram   = gold["per_gram"]
    per_10g    = gold["per_10g"]
    change     = gold["change"]
    change_pct = gold["change_pct"]

    st.markdown(f"""
    <div style='padding: 1.2rem 0 0.5rem 0'>
        <span style='font-size: 2.8rem; font-weight: 700;
                     color: var(--color-text-primary)'>
            ₹{per_gram:,.0f}
        </span>
        <span style='font-size: 1.1rem;
                     color: var(--color-text-secondary);
                     margin-left: 10px'>
            per gram · 24K · Source: NSE GOLDBEES
        </span>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("💛 Per Gram (24K)",
                f"₹{per_gram:,.0f}",
                f"₹{change:+.0f} ({change_pct:+.2f}%) today")
    col2.metric("💛 Per 10 Grams (24K)",
                f"₹{per_10g:,.0f}",
                f"₹{change*10:+.0f} today")
    col3.metric("📡 Live Source",
                "NSE: GOLDBEES",
                "Direct INR · No conversion")

    st.caption("ℹ️ Price = NSE GOLDBEES ETF (tracks MCX gold). "
               "Jeweller rates include GST (3%) + making charges on top.")
else:
    st.error("Could not fetch live price. NSE may be closed or yfinance unavailable.")
    per_gram = 0
    change = change_pct = 0

st.divider()

# ── Chart + period buttons ─────────────────────────────────────────────────────
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
    hist = get_history(period, interval)

if hist is not None and len(hist) > 1:
    import altair as alt

    df_chart = hist.reset_index()
    df_chart.columns = ["Date", "₹ per gram (24K)"]
    df_chart["Date"] = pd.to_datetime(df_chart["Date"])

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
                axis=alt.Axis(title="₹ per gram", format=",.0f")),
        tooltip=[
            alt.Tooltip("Date:T", format="%d %b %Y"),
            alt.Tooltip("₹ per gram (24K):Q",
                        format=",.0f", title="₹/gram")
        ]
    ).properties(height=360)

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
    st.info("Historical data unavailable. NSE may be closed right now.")

st.divider()

# ── Change summary table ───────────────────────────────────────────────────────
st.subheader("📊 Change Summary")

SUMMARY_PERIODS = [
    ("1 Day",    "2d",  "1h"),
    ("1 Week",   "5d",  "1h"),
    ("1 Month",  "1mo", "1d"),
    ("3 Months", "3mo", "1d"),
    ("1 Year",   "1y",  "1wk"),
]

rows = []
for label, p, iv in SUMMARY_PERIODS:
    data = get_history(p, iv)
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
    st.info("Summary data unavailable. NSE may be closed.")

st.divider()

# ── AI Chat ────────────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "system",
            "content": (
                "You are an expert financial assistant for Indian gold investors. "
                "You receive live 24K gold prices in INR from NSE GOLDBEES ETF. "
                "Give practical advice on: physical gold (coins/bars), "
                "Sovereign Gold Bonds (SGBs — 2.5% annual interest, tax-free on maturity), "
                "Gold ETFs (like GOLDBEES, SBI Gold), digital gold, and jewellery. "
                "Factor in Indian taxes: LTCG (>3 years = 12.5% without indexation post-2024 budget), "
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

    context = f"""[Live Market Data — INR · Source: NSE GOLDBEES]
- 24K gold: ₹{per_gram:,.0f}/gram | ₹{per_10g:,.0f}/10g
- Today's change: ₹{change:+.0f}/gram ({change_pct:+.2f}%)
- Period changes:
{summary_lines}
"""
    full_msg = f"{context}\nUser question: {question}"
    st.session_state.messages.append({"role": "user", "content": full_msg})

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
                st.session_state.messages.append(
                    {"role": "assistant", "content": answer}
                )
            except Exception as e:
                st.error(f"AI Error: {str(e)}")

st.divider()
st.caption(
    "⚠️ Not SEBI-registered financial advice. "
    "Prices from NSE GOLDBEES ETF. "
    "Jeweller rates include GST & making charges. "
    "Consult a registered advisor before investing."
)