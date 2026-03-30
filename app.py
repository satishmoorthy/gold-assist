import streamlit as st
from openai import OpenAI
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ── OpenRouter Client ──────────────────────────────────────────────────────────
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

BASE_URL = "https://api.gold-api.com"  # 100% free, no key, no rate limits

# ── Gold Data Functions ────────────────────────────────────────────────────────
@st.cache_data(ttl=60)  # cache 60 seconds — safe since API is unlimited
def get_gold_price():
    """Real-time gold spot price — no API key needed."""
    try:
        r = requests.get(f"{BASE_URL}/price/XAU", timeout=5)
        d = r.json()
        return {
            "price": d.get("price", "N/A"),
            "change": d.get("ch", 0),
            "change_pct": d.get("chp", 0),
            "timestamp": d.get("updatedAt", "")
        }
    except Exception as e:
        return {"price": "N/A", "change": 0, "change_pct": 0, "timestamp": ""}

@st.cache_data(ttl=3600)  # cache 1 hour — historical data doesn't change often
def get_gold_history(days=30):
    """Fetch OHLC historical data for the past N days."""
    results = []
    try:
        end = datetime.now(datetime.UTC)
        for i in range(days, 0, -2):  # every 2 days to keep it light
            date_str = (end - timedelta(days=i)).strftime("%Y-%m-%d")
            r = requests.get(f"{BASE_URL}/history/XAU/{date_str}", timeout=5)
            if r.status_code == 200:
                d = r.json()
                if d.get("price"):
                    results.append({
                        "date": date_str,
                        "price": d["price"],
                        "open": d.get("open", d["price"]),
                        "high": d.get("high", d["price"]),
                        "low": d.get("low", d["price"]),
                    })
    except Exception:
        pass
    return results

# ── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gold Assist", page_icon="💰", layout="wide")
st.title("💰 Gold Assist")
st.caption("AI-powered gold investment advisor • Live data by gold-api.com (free, unlimited)")

# ── Live Price Metrics ─────────────────────────────────────────────────────────
gold = get_gold_price()

if gold["price"] != "N/A":
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🥇 Gold Spot (XAU/USD)", f"${gold['price']:,.2f}")
    delta_color = "normal"
    col2.metric("📈 24h Change ($)", f"${gold['change']:+.2f}")
    col3.metric("📊 24h Change (%)", f"{gold['change_pct']:+.2f}%")
    col4.metric("🕐 Last Updated", gold["timestamp"][:16] if gold["timestamp"] else "Live")
else:
    st.warning("⚠️ Could not fetch live gold price.")

# ── Historical Chart ───────────────────────────────────────────────────────────
with st.expander("📉 30-Day Gold Price Trend", expanded=True):
    with st.spinner("Loading historical data..."):
        history = get_gold_history(30)
    if history:
        import pandas as pd
        df = pd.DataFrame(history)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        col_chart, col_stats = st.columns([3, 1])
        with col_chart:
            st.line_chart(df.set_index("date")["price"], use_container_width=True)

        with col_stats:
            st.markdown("**30-Day Stats**")
            st.metric("High", f"${df['high'].max():,.2f}")
            st.metric("Low", f"${df['low'].min():,.2f}")
            st.metric("Avg", f"${df['price'].mean():,.2f}")
            price_change = df['price'].iloc[-1] - df['price'].iloc[0]
            st.metric("Range Move", f"${price_change:+.2f}")
    else:
        st.info("Historical data temporarily unavailable.")

st.divider()

# ── Chat ───────────────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "system",
            "content": (
                "You are an expert financial assistant specializing in gold investments. "
                "You will be given real-time gold price data and 30-day trend context with each user message. "
                "Give clear, practical advice about: current price analysis, market trends, "
                "risks vs benefits, investment strategies (physical gold, ETFs, sovereign gold bonds, "
                "mining stocks, digital gold), and how gold compares to other assets like equities and crypto. "
                "Be concise and data-driven. Always remind users this is not professional financial advice."
            )
        }
    ]

for msg in st.session_state.messages[1:]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

question = st.chat_input("Ask about gold investment... e.g. 'Is now a good time to buy gold?'")

if question:
    # Build rich context for the AI
    trend_summary = ""
    if history and len(history) >= 2:
        first_price = history[0]["price"]
        last_price = history[-1]["price"]
        high_30 = max(h["high"] for h in history)
        low_30 = min(h["low"] for h in history)
        trend_summary = (
            f"30-day trend: started at ${first_price:,.2f}, now ${last_price:,.2f} "
            f"(30d high: ${high_30:,.2f}, 30d low: ${low_30:,.2f})"
        )

    context = f"""[Live Market Data]
- Current Gold Price: ${gold['price']:,.2f} USD/troy oz
- 24h Change: ${gold['change']:+.2f} ({gold['change_pct']:+.2f}%)
- {trend_summary}
- Data source: gold-api.com (real-time, free)
"""

    full_message = f"{context}\nUser question: {question}"
    st.session_state.messages.append({"role": "user", "content": full_message})

    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing..."):
            try:
                response = client.chat.completions.create(
                    model="meta-llama/llama-3.3-70b-instruct:free",
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