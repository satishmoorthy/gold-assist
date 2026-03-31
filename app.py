import streamlit as st
from openai import OpenAI
import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

BASE_URL = "https://api.gold-api.com"
USD_INR_URL = "https://open.er-api.com/v6/latest/USD"  # free, no key needed

# ── Fetch live USD/INR rate ────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_usd_inr():
    try:
        r = requests.get(USD_INR_URL, timeout=5)
        return r.json()["rates"]["INR"]
    except:
        return 83.5  # fallback rate

# ── Fetch live gold price ──────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_gold_price():
    try:
        r = requests.get(f"{BASE_URL}/price/XAU", timeout=5)
        d = r.json()
        return {
            "price": d.get("price", 0),
            "change": d.get("ch", 0),
            "change_pct": d.get("chp", 0),
            "timestamp": d.get("updatedAt", "")
        }
    except:
        return {"price": 0, "change": 0, "change_pct": 0, "timestamp": ""}

# ── Fetch 30-day historical data ───────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_gold_history():
    prices = []
    dates = []
    today = datetime.now(timezone.utc)
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        # skip weekends (markets closed)
        if day.weekday() >= 5:
            continue
        date_str = day.strftime("%Y%m%d")
        label = day.strftime("%d %b")
        try:
            r = requests.get(f"{BASE_URL}/price/XAU/{date_str}", timeout=5)
            if r.status_code == 200:
                d = r.json()
                price = d.get("price", 0)
                if price and price > 0:
                    prices.append(price)
                    dates.append(label)
        except:
            continue
    return dates, prices

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gold Assist", page_icon="💰", layout="wide")
st.title("💰 Gold Assist")
st.caption("AI-powered gold investment advisor • Live data by gold-api.com (free, unlimited)")

# ── Fetch data ─────────────────────────────────────────────────────────────────
gold = get_gold_price()
inr_rate = get_usd_inr()

usd_price = gold["price"]
troy_oz_to_gram = 31.1035
price_per_gram_usd = usd_price / troy_oz_to_gram
price_per_gram_inr = price_per_gram_usd * inr_rate
price_per_10g_inr = price_per_gram_inr * 10

# ── USD Metrics ────────────────────────────────────────────────────────────────
st.subheader("🌍 International Price (USD)")
col1, col2, col3, col4 = st.columns(4)
col1.metric("🥇 Gold Spot (XAU/USD)", f"${usd_price:,.2f}")
col2.metric("📈 24h Change ($)", f"${gold['change']:+.2f}")
col3.metric("📊 24h Change (%)", f"{gold['change_pct']:+.2f}%")
col4.metric("🕐 Last Updated", gold["timestamp"][:16] if gold["timestamp"] else "Live")

st.divider()

# ── Indian Price (24K) ─────────────────────────────────────────────────────────
st.subheader("🇮🇳 Indian Price (24K Gold)")
col1, col2, col3 = st.columns(3)
col1.metric("💛 Per Gram (24K)", f"₹{price_per_gram_inr:,.0f}")
col2.metric("💛 Per 10 Grams (24K)", f"₹{price_per_10g_inr:,.0f}")
col3.metric("💱 USD/INR Rate", f"₹{inr_rate:.2f}")
st.caption("ℹ️ Indian price = spot price converted at live USD/INR rate. Jeweller rates may include GST (3%) + making charges.")

st.divider()

# ── 30-Day Chart ───────────────────────────────────────────────────────────────
with st.expander("📉 30-Day Gold Price Trend (USD/oz)", expanded=True):
    with st.spinner("Loading historical data..."):
        dates, prices = get_gold_history()

    if prices and len(prices) > 1:
        import pandas as pd
        df = pd.DataFrame({"Date": dates, "Price (USD/oz)": prices})
        df = df.set_index("Date")

        col_chart, col_stats = st.columns([3, 1])
        with col_chart:
            st.line_chart(df, use_container_width=True)
        with col_stats:
            st.markdown("**30-Day Stats**")
            st.metric("High", f"${max(prices):,.2f}")
            st.metric("Low", f"${min(prices):,.2f}")
            st.metric("Avg", f"${sum(prices)/len(prices):,.2f}")
            change_30d = prices[-1] - prices[0]
            change_30d_pct = (change_30d / prices[0]) * 100
            st.metric("30d Move", f"${change_30d:+.2f}", f"{change_30d_pct:+.2f}%")
    else:
        st.info("Historical data temporarily unavailable.")

st.divider()

# ── Chat ───────────────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "system",
            "content": (
                "You are an expert financial assistant specializing in gold investments for Indian investors. "
                "You will be given real-time gold price data including USD and INR prices. "
                "Give clear, practical advice about: current price analysis, market trends, "
                "risks vs benefits, and investment strategies like physical gold (coins/bars), "
                "Sovereign Gold Bonds (SGBs), Gold ETFs, digital gold, and jewellery. "
                "Always mention Indian-specific options like SGBs which give 2.5% annual interest. "
                "Be concise and data-driven. Always remind users this is not professional financial advice."
            )
        }
    ]

for msg in st.session_state.messages[1:]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

question = st.chat_input("Ask about gold investment... e.g. 'Is now a good time to buy gold in India?'")

if question:
    trend_summary = ""
    if prices and len(prices) >= 2:
        trend_summary = (
            f"30-day trend: from ${prices[0]:,.2f} to ${prices[-1]:,.2f} "
            f"(30d high: ${max(prices):,.2f}, 30d low: ${min(prices):,.2f})"
        )

    context = f"""[Live Market Data]
- Gold spot price: ${usd_price:,.2f} USD/troy oz
- 24h change: ${gold['change']:+.2f} ({gold['change_pct']:+.2f}%)
- Indian 24K price: ₹{price_per_gram_inr:,.0f}/gram | ₹{price_per_10g_inr:,.0f}/10g
- USD/INR rate: ₹{inr_rate:.2f}
- {trend_summary}
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
st.caption("⚠️ Not financial advice. Consult a SEBI-registered advisor before investing.")