import os
import json
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, date, time as dt_time
from zoneinfo import ZoneInfo
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 網頁基本設定
st.set_page_config(page_title="美股量化潛伏狙擊系統 5.0", page_icon="🎯", layout="wide")

# ==========================================
# 6位數簡易通行碼 (PIN) 記憶保險箱引擎
# ==========================================
VAULT_FILE = "pin_vault_v5.json"

DEFAULT_STATE = {
    "capital": 10000.0,
    "risk_pct": 1.5,
    "atr_mult": 2.0,
    "strategy_mode": "🎯 潛伏起漲狙擊 (爆發前佈局/不追高)",
    "custom_watchlist": "NVDA, TSLA, PLTR, AMD",
    "last_selected_ticker": "NVDA",
    "auto_pick_count": 15,
    "portfolio": [
        {"Ticker": "NVDA", "Shares": 10.0, "Avg_Cost": 120.0}
    ]
}

def load_vault():
    if os.path.exists(VAULT_FILE):
        try:
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_to_vault(pin_code, user_data):
    vault = load_vault()
    vault[pin_code.upper()] = user_data
    try:
        with open(VAULT_FILE, "w", encoding="utf-8") as f:
            json.dump(vault, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

query_pin = st.query_params.get("pin", "888999").upper()
if "current_pin" not in st.session_state:
    st.session_state.current_pin = query_pin

vault_db = load_vault()
if "user_state" not in st.session_state:
    if st.session_state.current_pin in vault_db:
        saved = vault_db[st.session_state.current_pin]
        merged = DEFAULT_STATE.copy()
        merged.update(saved)
        st.session_state.user_state = merged
    else:
        st.session_state.user_state = DEFAULT_STATE.copy()
        save_to_vault(st.session_state.current_pin, st.session_state.user_state)

def sync_state():
    save_to_vault(st.session_state.current_pin, st.session_state.user_state)

state = st.session_state.user_state

# ==========================================
# 內建市場母體池 (供系統自動海選最具爆發潛力標的)
# ==========================================
MARKET_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "NFLX",
    "AMD", "AVGO", "TSM", "MU", "ARM", "SMCI", "MRVL", "ANET", "VRT", "DELL",
    "PLTR", "CRWD", "PANW", "NOW", "SNOW", "ORCL", "CRM", "SHOP", "APP", "IOT",
    "JPM", "GS", "V", "MA", "AXP", "COIN", "HOOD", "SOFI", "MSTR",
    "LLY", "ISRG", "UNH", "COST", "WMT", "UBER", "CAT", "GE", "XOM", "CEG", "VST"
]

# ==========================================
# 美股開休市狀態自動偵測器 (美東時間 ET & 台灣時間)
# ==========================================
def get_us_market_status():
    now_et = datetime.now(ZoneInfo("America/New_York"))
    now_tw = datetime.now(ZoneInfo("Asia/Taipei"))
    
    us_holidays = {
        date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
        date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
        date(2026, 11, 26), date(2026, 12, 25)
    }
    
    weekday = now_et.weekday()
    curr_time = now_et.time()
    open_t, close_t, pre_t, after_t = dt_time(9, 30), dt_time(16, 0), dt_time(4, 0), dt_time(20, 0)
    
    if weekday >= 5 or now_et.date() in us_holidays:
        status_badge = "🔴 美股休市中 (週末 / 國定假日休市)"
        detail = "目前為休市時段，系統正好適合用來篩選下週「壓縮蓄勢、即將爆發」的潛伏標的！"
    elif open_t <= curr_time < close_t:
        close_dt = datetime.combine(now_et.date(), close_t, tzinfo=ZoneInfo("America/New_York"))
        rem = close_dt - now_et
        hrs, rem_s = divmod(int(rem.total_seconds()), 3600)
        mins = rem_s // 60
        status_badge = f"🟢 美股正規盤交易中 (Market OPEN) ｜ 距離收盤剩餘 {hrs}小時 {mins}分"
        detail = "盤中即時報價與起漲拐點偵測運作中！"
    elif pre_t <= curr_time < open_t:
        open_dt = datetime.combine(now_et.date(), open_t, tzinfo=ZoneInfo("America/New_York"))
        rem = open_dt - now_et
        hrs, rem_s = divmod(int(rem.total_seconds()), 3600)
        mins = rem_s // 60
        status_badge = f"🌅 美股盤前交易時段 (Pre-Market) ｜ 距離正式開盤剩餘 {hrs}小時 {mins}分"
        detail = "即將開盤，可先鎖定下方「潛伏評分最高」的標的準備卡位。"
    elif close_t <= curr_time < after_t:
        status_badge = "🌙 美股盤後交易時段 (After-Hours)"
        detail = "正規盤已收盤，目前為盤後電子盤交易時段。"
    else:
        status_badge = "🔴 美股夜盤休市中"
        detail = "等待美東時間 04:00 盤前開市。"
        
    time_str = f"🗽 美東時間: {now_et.strftime('%Y-%m-%d %H:%M')} ET ｜ 🇹🇼 台灣時間: {now_tw.strftime('%Y-%m-%d %H:%M')}"
    return status_badge, detail, time_str

st.title("🎯 美股量化「爆發前潛伏狙擊」系統 5.0")
st.caption("專注於：VCP 波動壓縮蓄勢 ｜ 主力橫盤背離暗池吃貨 ｜ 均線支撐黃金買點 ｜ 拒絕高檔追高")
mkt_badge, mkt_detail, mkt_clock = get_us_market_status()
st.info(f"**{mkt_badge}** \n🕒 {mkt_clock} ｜ 💡 {mkt_detail}")

# ==========================================
# 側邊欄：6位數記憶通行碼、策略模式切換與風控
# ==========================================
st.sidebar.header("🔑 6位數專屬記憶通行碼")
col_pin1, col_pin2 = st.sidebar.columns([2, 1.2])
with col_pin1:
    pin_input = st.text_input("專屬通行碼", value=st.session_state.current_pin, max_chars=10, label_visibility="collapsed").strip().upper()
with col_pin2:
    if st.button("載入/切換", use_container_width=True):
        if pin_input:
            st.session_state.current_pin = pin_input
            st.query_params["pin"] = pin_input
            v_db = load_vault()
            if pin_input in v_db:
                merged = DEFAULT_STATE.copy()
                merged.update(v_db[pin_input])
                st.session_state.user_state = merged
                st.sidebar.success(f"✅ 已載入 [{pin_input}]！")
            else:
                save_to_vault(pin_input, st.session_state.user_state)
                st.sidebar.success(f"✨ 已建立 [{pin_input}]！")
            st.rerun()

st.sidebar.markdown(f"📌 目前綁定記憶碼：**`{st.session_state.current_pin}`**")
st.sidebar.divider()

st.sidebar.subheader("🧠 選股核心策略模式")
mode_options = [
    "🎯 潛伏起漲狙擊 (爆發前佈局/不追高)",
    "🚀 右側動能突破 (追隨已爆發強勢股)"
]
curr_mode_idx = 0 if "潛伏" in state.get("strategy_mode", "") else 1
new_mode = st.sidebar.radio("選擇演算法評分邏輯：", mode_options, index=curr_mode_idx,
                            help="【潛伏起漲狙擊】專門尋找還沒大漲、布林壓縮蓄勢、主力偷偷吃貨或剛回測均線支撐的起漲前標的，若已經漲太多反而會扣分防追高！")

auto_refresh = st.sidebar.toggle("⚡ 開啟盤中自動更新", value=False)
refresh_sec = st.sidebar.selectbox("自動更新頻率 (秒)", [60, 180, 300], index=1)

st.sidebar.subheader("🤖 系統海選 + 自選清單")
new_auto_count = st.sidebar.slider("系統自動海選標的數量", min_value=5, max_value=25, value=int(state["auto_pick_count"]), step=1)
new_watchlist = st.sidebar.text_area("⭐ 我的自選觀察清單 (逗號分隔)", value=state["custom_watchlist"], height=70)

st.sidebar.subheader("🛡️ 預算與量化風控 (自動記憶)")
new_capital = st.sidebar.number_input("💰 我的總投資預算 (USD)", min_value=500.0, value=float(state["capital"]), step=500.0)
new_risk = st.sidebar.slider("單筆最大承受虧損 (%)", 0.5, 5.0, float(state["risk_pct"]), 0.5)
new_atr = st.sidebar.slider("ATR 停損寬度 (倍)", 1.0, 4.0, float(state["atr_mult"]), 0.5)

if (new_mode != state.get("strategy_mode") or new_auto_count != state["auto_pick_count"] or 
    new_watchlist != state["custom_watchlist"] or new_capital != state["capital"] or 
    new_risk != state["risk_pct"] or new_atr != state["atr_mult"]):
    state["strategy_mode"] = new_mode
    state["auto_pick_count"] = new_auto_count
    state["custom_watchlist"] = new_watchlist
    state["capital"] = new_capital
    state["risk_pct"] = new_risk
    state["atr_mult"] = new_atr
    sync_state()

user_custom_list = [t.strip().upper() for t in state["custom_watchlist"].split(",") if t.strip()]
portfolio_tickers = [str(item.get("Ticker", "")).strip().upper() for item in state["portfolio"] if item.get("Ticker")]

# ==========================================
# 輔助函數：全中文財報基本面 ＆ 華爾街外電自動中文化
# ==========================================
RATING_MAP_ZH = {
    "STRONG_BUY": "🔥 強力買進", "BUY": "📈 買進", "HOLD": "👀 觀望持有",
    "UNDERPERFORM": "⚠️ 表現落後", "SELL": "🚨 賣出", "NONE": "暫無評級", "N/A": "暫無評級"
}

@st.cache_data(ttl=1800)
def get_earnings_and_fundamentals(sym):
    res = {
        "earnings_str": "未知", "days_to_earnings": 999,
        "pe_forward": None, "rev_growth": None, "profit_margin": None,
        "target_price": None, "recommendation_zh": "暫無評級"
    }
    try:
        tk = yf.Ticker(sym)
        cal = tk.calendar
        e_date = None
        if isinstance(cal, dict) and 'Earnings Date' in cal and len(cal['Earnings Date']) > 0:
            e_date = cal['Earnings Date'][0]
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            if 'Earnings Date' in cal.index:
                e_date = cal.loc['Earnings Date'].iloc[0]
            elif 'Earnings Date' in cal.columns:
                e_date = cal['Earnings Date'].iloc[0]
                
        if e_date is not None:
            if isinstance(e_date, (datetime, pd.Timestamp)):
                e_date = e_date.date()
            if isinstance(e_date, date):
                days_diff = (e_date - date.today()).days
                res["days_to_earnings"] = days_diff
                if 0 <= days_diff <= 14:
                    res["earnings_str"] = f"⚠️ {e_date.strftime('%m/%d')} ({days_diff}天後)"
                elif days_diff > 14:
                    res["earnings_str"] = f"📅 {e_date.strftime('%m/%d')} ({days_diff}天後)"
                else:
                    res["earnings_str"] = f"已公布 ({e_date.strftime('%m/%d')})"
                    
        info = tk.info
        if isinstance(info, dict):
            res["pe_forward"] = info.get("forwardPE")
            res["rev_growth"] = info.get("revenueGrowth")
            res["profit_margin"] = info.get("profitMargins")
            res["target_price"] = info.get("targetMeanPrice")
            raw_rec = str(info.get("recommendationKey", "N/A")).upper()
            res["recommendation_zh"] = RATING_MAP_ZH.get(raw_rec, raw_rec)
    except Exception:
        pass
    return res

def translate_to_zh(text):
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-TW&dt=t&q={urllib.parse.quote(text)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode('utf-8'))
            return "".join([part[0] for part in data[0] if part[0]])
    except Exception:
        return text

@st.cache_data(ttl=300)
def fetch_zh_wallstreet_news(sym, is_macro=False):
    news_items = []
    try:
        query = "US+stock+market+Wall+Street+Fed+S%26P500" if is_macro else f"{sym}+stock+wall+street+earnings"
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            root = ET.fromstring(response.read())
            for item in root.findall('.//item')[:7]:
                title_en = item.find('title').text if item.find('title') is not None else ""
                clean_en = title_en.rsplit(" - ", 1)[0] if " - " in title_en else title_en
                title_zh = translate_to_zh(clean_en)
                link = item.find('link').text if item.find('link') is not None else ""
                pub = item.find('source').text if item.find('source') is not None else "華爾街外電"
                pub_date = item.find('pubDate').text[:16] if item.find('pubDate') is not None else ""
                if title_en:
                    news_items.append({"title_zh": title_zh, "title_en": clean_en, "link": link, "publisher": pub, "time": pub_date})
    except Exception:
        pass
    return news_items

# ==========================================
# 模組一：全方位宏觀與市場情緒中心
# ==========================================
st.subheader("🧭 模組一：市場情緒溫度計與全方位大盤雷達")

@st.cache_data(ttl=120)
def get_macro_dashboard():
    symbols = ["^VIX", "SPY", "QQQ", "^SOX", "IWM", "^TNX"]
    data = yf.download(symbols, period="6mo", interval="1d", progress=False)
    close = data['Close'] if isinstance(data.columns, pd.MultiIndex) else data
    metrics = {}
    for sym in symbols:
        if sym in close.columns:
            s = close[sym].dropna()
            if len(s) >= 50:
                curr, prev = float(s.iloc[-1]), float(s.iloc[-2])
                metrics[sym] = {
                    "curr": curr, "chg_pct": ((curr - prev) / prev) * 100, "chg_abs": curr - prev,
                    "ma20": float(s.rolling(20).mean().iloc[-1]), "ma50": float(s.rolling(50).mean().iloc[-1])
                }
    return metrics

try:
    m_data = get_macro_dashboard()
    vix, vix_diff = m_data["^VIX"]["curr"], m_data["^VIX"]["chg_abs"]
    col_gauge, col_metrics = st.columns([1.3, 2.7])
    
    with col_gauge:
        vix_status = "🟢 極度樂觀 (勿追高/找低位階潛伏)" if vix < 15 else ("🟢 穩定偏多 (適合佈局壓縮突破)" if vix < 20 else ("🟠 警戒震盪 (逢回測均線買黑不買紅)" if vix < 30 else "🔴 極度恐慌 (等待底部背離信號)"))
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta", value=vix,
            delta={'reference': vix - vix_diff, 'increasing': {'color': "#ef5350"}, 'decreasing': {'color': "#26a69a"}},
            title={'text': f"<b>VIX 恐慌指數</b><br><span style='font-size:13px;color:gray'>{vix_status}</span>"},
            gauge={
                'axis': {'range': [10, 45], 'tickwidth': 1}, 'bar': {'color': "white", 'thickness': 0.25},
                'steps': [
                    {'range': [10, 15], 'color': "rgba(38, 166, 154, 0.45)"},
                    {'range': [15, 20], 'color': "rgba(102, 187, 106, 0.35)"},
                    {'range': [20, 30], 'color': "rgba(255, 167, 38, 0.45)"},
                    {'range': [30, 45], 'color': "rgba(239, 83, 80, 0.55)"}
                ],
                'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 30}
            }
        ))
        fig_gauge.update_layout(height=230, margin=dict(l=20, r=20, t=50, b=10), template="plotly_dark")
        st.plotly_chart(fig_gauge, use_container_width=True)

    with col_metrics:
        c1, c2, c3 = st.columns(3)
        spy, qqq, sox, iwm, tnx = m_data["SPY"], m_data["QQQ"], m_data["^SOX"], m_data["IWM"], m_data["^TNX"]
        c1.metric("標普 500 (SPY)", f"${spy['curr']:.2f}", f"{spy['chg_pct']:+.2f}%")
        c2.metric("納斯達克 (QQQ)", f"${qqq['curr']:.2f}", f"{qqq['chg_pct']:+.2f}%")
        c3.metric("費城半導體 (^SOX)", f"{sox['curr']:.1f}", f"{sox['chg_pct']:+.2f}%")
        c4, c5, c6 = st.columns(3)
        c4.metric("羅素 2000 (IWM)", f"${iwm['curr']:.2f}", f"{iwm['chg_pct']:+.2f}%")
        c5.metric("10年期美債殖利率 (^TNX)", f"{tnx['curr']:.2f}%", f"{tnx['chg_abs']:+.2f}", delta_color="inverse")
        with c6:
            st.markdown("##### 📌 潛伏與進場時機診斷")
            if vix < 20 and spy['curr'] > spy['ma20']:
                st.success("**🟢 適合潛伏與點火卡位**：大盤健康，優先鎖定下方「🔋壓縮蓄勢」或「🎯口袋支點剛起漲」標的。")
            elif vix >= 25 or spy['curr'] < spy['ma50']:
                st.error("**🔴 嚴控風險**：大盤弱勢，僅能小倉位試單「🐳主力逆勢高吸籌」且守穩年線的標的。")
            else:
                st.warning("**🟡 買黑不買紅**：大盤震盪，切忌追高，專挑「⚓回測均線支撐」且離20MA乖離小的標的。")
except Exception as e:
    st.warning(f"正在同步大盤宏觀數據... ({e})")

st.divider()

# ==========================================
# 5.0 核心引擎：偵測「起漲前壓縮、主力背離吸籌、均線支撐買點」
# ==========================================
@st.cache_data(ttl=180)
def run_sniper_screener(universe_list, custom_list, port_list, auto_top_n, total_cap, risk_p, atr_m, mode_str):
    all_symbols = list(dict.fromkeys(universe_list + custom_list + port_list))
    data = yf.download(all_symbols, period="1y", interval="1d", group_by="ticker", progress=False)
    
    is_sniper_mode = "潛伏" in mode_str
    scored_items = []
    raw_histories = {}
    price_lookup = {}
    atr_stop_lookup = {}
    
    for sym in all_symbols:
        try:
            df = data[sym].dropna() if len(all_symbols) > 1 else data.dropna()
            if len(df) < 200:
                continue
            raw_histories[sym] = df
            
            close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
            curr_p = float(close.iloc[-1])
            prev_p = float(close.iloc[-2])
            pct_chg = ((curr_p - prev_p) / prev_p) * 100
            price_lookup[sym] = curr_p
            
            # 1. 均線與乖離率 (Bias - 判斷是否已經漲太多或剛好在起漲支撐點)
            ma10 = float(close.rolling(10).mean().iloc[-1])
            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = float(close.rolling(50).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1])
            dist_ma20_pct = ((curr_p - ma20) / ma20) * 100 # 距離月線乖離率 (%)
            dist_ma50_pct = ((curr_p - ma50) / ma50) * 100
            
            # 2. 布林通道壓縮率 (BB Width - 判斷是否處於爆發前夕的彈簧壓縮狀態)
            std20 = float(close.rolling(20).std().iloc[-1])
            bb_width_pct = ((4 * std20) / ma20) * 100 if ma20 > 0 else 20.0
            
            # 過去 10 日漲跌幅 (判斷是否處於橫盤洗盤期)
            ret_10d_pct = ((curr_p - float(close.iloc[-11])) / float(close.iloc[-11])) * 100 if len(close) > 11 else 0.0
            
            # 3. 成交量比 (RVOL) 與 口袋支點 (Pocket Pivot: 成交量大於過去10天所有下跌日的成交量)
            avg_vol20 = float(vol.rolling(20).mean().iloc[-1])
            rvol = float(vol.iloc[-1]) / avg_vol20 if avg_vol20 > 0 else 1.0
            
            recent_10_chg = close.diff().tail(11).iloc[:-1]
            recent_10_vol = vol.tail(11).iloc[:-1]
            down_vols = recent_10_vol[recent_10_chg < 0]
            max_down_vol = float(down_vols.max()) if not down_vols.empty else 0.0
            is_pocket_pivot = (pct_chg > 0.5) and (float(vol.iloc[-1]) > max_down_vol) and (curr_p >= ma10) and (-1.5 <= dist_ma20_pct <= 5.5)
            
            # 4. CMF 主力資金流 & OBV 能量潮是否領先創高 (偵測暗池提前吃貨)
            mfm = ((close - low) - (high - close)) / (high - low + 1e-9)
            cmf20 = float((mfm * vol).rolling(20).sum().iloc[-1] / (vol.rolling(20).sum().iloc[-1] + 1e-9))
            
            obv = (vol * close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))).cumsum()
            obv_high_20 = float(obv.tail(20).max())
            price_high_20 = float(close.tail(20).max())
            # OBV 已經創20日新高(或接近98%)，但股價還沒創20日新高 = 主力偷偷把籌碼買光了！
            is_obv_leading = (float(obv.iloc[-1]) >= obv_high_20 * 0.98) and (curr_p < price_high_20 * 0.97)
            
            # 5. RSI 與 MACD 動能拐點 (綠柱縮腳或剛金叉)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi14 = float(100 - (100 / (1 + (gain / (loss + 1e-9)).iloc[-1])))
            
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd_hist = macd_line - signal_line
            hist_curr, hist_prev = float(macd_hist.iloc[-1]), float(macd_hist.iloc[-2])
            # MACD 剛金叉 或 水下綠柱連續縮腳準備翻紅
            is_macd_turning_up = (hist_curr > 0 and hist_prev <= 0) or (hist_curr > hist_prev and hist_curr > -0.8)
            
            # 6. ATR 停損與倉位計算
            tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
            stop_loss_price = curr_p - (atr_m * atr14)
            atr_stop_lookup[sym] = stop_loss_price
            risk_per_share = curr_p - stop_loss_price
            suggested_shares = int((total_cap * (risk_p / 100.0)) // risk_per_share) if risk_per_share > 0 else 0

            # ==========================================================
            # 🎯 核心差異：雙模式評分引擎 (潛伏起漲狙擊 vs 右側追強)
            # ==========================================================
            if is_sniper_mode:
                # 【模式 A：潛伏起漲狙擊評分 (滿分 100，專抓爆發前夕、嚴懲追高)】
                # 1. 潛伏位置與不追高得分 (滿分 30 分)：離 20MA 越近(-2%~+3.5%)且長線>200MA 最高分；若乖離 >8% 嚴重扣分！
                pos_pts = 0
                if curr_p > ma200: pos_pts += 10
                if -2.5 <= dist_ma20_pct <= 3.5:
                    pos_pts += 20 # 完美貼近月線起漲點
                elif -4.0 <= dist_ma50_pct <= 2.5 and curr_p > ma200:
                    pos_pts += 18 # 完美回測季線黃金支撐
                elif 3.5 < dist_ma20_pct <= 6.5:
                    pos_pts += 10
                elif dist_ma20_pct > 8.5:
                    pos_pts -= 15 # 已經漲太多了！直接扣分防止追高
                    
                # 2. 主力暗池背離吃貨得分 (滿分 30 分)：CMF 越高越好，若股價橫盤但 CMF>0.08 或 OBV 領先創高再加分
                cmf_clamped = max(-0.20, min(0.25, cmf20))
                stealth_pts = int(((cmf_clamped + 0.20) / 0.45) * 22)
                if (abs(ret_10d_pct) <= 5.0 and cmf20 >= 0.08) or is_obv_leading:
                    stealth_pts += 8 # 股價沒漲但主力狂買 (背離吸籌)
                    
                # 3. 波動壓縮蓄勢 VCP / 布林收斂得分 (滿分 20 分)：布林通道越窄代表彈簧壓越緊
                if bb_width_pct <= 10.0:
                    squeeze_pts = 20
                elif bb_width_pct <= 15.0:
                    squeeze_pts = 15
                elif bb_width_pct <= 22.0:
                    squeeze_pts = 10
                else:
                    squeeze_pts = 4
                    
                # 4. 起漲點火觸發訊號 (滿分 20 分)：口袋支點、MACD 轉折向上、RSI 處於 42~62 剛起漲區
                trigger_pts = 0
                if is_pocket_pivot: trigger_pts += 9
                if is_macd_turning_up: trigger_pts += 6
                if 42 <= rsi14 <= 64: trigger_pts += 5
                elif 35 <= rsi14 < 42: trigger_pts += 4 # 超賣反彈區
                
                total_score = int(min(99, max(10, pos_pts + stealth_pts + squeeze_pts + trigger_pts)))
                
                # 判定潛伏階段與進場型態標籤
                if is_pocket_pivot and cmf20 > 0.05:
                    setup_tag = "🎯 口袋支點剛點火 (起漲第1根)"
                elif bb_width_pct <= 14.0 and cmf20 >= 0.06 and abs(dist_ma20_pct) <= 4.0:
                    setup_tag = "🔋 VCP 波動壓縮蓄勢 (爆發前夕)"
                elif (abs(ret_10d_pct) <= 4.5 and cmf20 >= 0.10) or is_obv_leading:
                    setup_tag = "🐳 主力橫盤暗池吃貨 (籌碼背離)"
                elif (-3.0 <= dist_ma20_pct <= 2.0 or -3.0 <= dist_ma50_pct <= 2.5) and curr_p > ma200 and cmf20 > 0:
                    setup_tag = "⚓ 回測均線黃金支撐 (低風險買點)"
                elif dist_ma20_pct > 8.0 or rsi14 > 72:
                    setup_tag = "⚠️ 短線已高 (乖離過大勿追高)"
                elif total_score <= 40:
                    setup_tag = "❄️ 籌碼渙散 / 空頭整理"
                else:
                    setup_tag = "👀 築底觀察中 (等待點火)"
            else:
                # 【模式 B：傳統右側動能突破評分】
                trend_pts = (12 if curr_p > ma20 else 0) + (10 if curr_p > ma50 else 0) + (10 if curr_p > ma200 else 0) + (8 if ma20 > ma50 > ma200 else 0)
                cmf_pts = int(((max(-0.25, min(0.25, cmf20)) + 0.25) / 0.50) * 30)
                rvol_pts = int(min(20, max(0, (rvol - 0.5) * 13))) if pct_chg >= 0 else int(max(0, 10 - (rvol - 0.8) * 10))
                rsi_pts = 10 if 50 <= rsi14 <= 72 else 5
                total_score = int(min(99, max(10, trend_pts + cmf_pts + rvol_pts + rsi_pts)))
                setup_tag = "🔥 強勢突破推進" if total_score >= 75 else "👀 區間震盪"

            scored_items.append({
                "sym": sym, "score": total_score, "setup_tag": setup_tag,
                "curr_p": curr_p, "pct_chg": pct_chg, "dist_ma20": dist_ma20_pct,
                "bb_width": bb_width_pct, "trend_20d": close.tail(20).tolist(),
                "cmf20": cmf20, "rvol": rvol, "rsi14": rsi14,
                "stop_loss": stop_loss_price, "shares": suggested_shares
            })
        except Exception:
            continue
            
    scored_items.sort(key=lambda x: (x["score"], x["cmf20"]), reverse=True)
    
    final_rows = []
    auto_picked_count = 0
    for item in scored_items:
        sym = item["sym"]
        is_custom = sym in custom_list
        is_port = sym in port_list
        
        if auto_picked_count < auto_top_n or is_custom or is_port:
            if not is_custom and not is_port:
                auto_picked_count += 1
                
            tags = []
            if is_port: tags.append("💼持倉")
            if is_custom: tags.append("⭐自選")
            if not tags or item["score"] >= 72: tags.append("🤖系統潛伏優選")
            source_tag = " / ".join(tags)
            
            f_info = get_earnings_and_fundamentals(sym)
            setup_display = f"🚨 財報將至 ({f_info['days_to_earnings']}天)" if 0 <= f_info["days_to_earnings"] <= 7 else item["setup_tag"]
                
            final_rows.append({
                "代號": sym,
                "入選來源": source_tag,
                "潛伏狙擊分": item["score"],
                "爆發前夕型態": setup_display,
                "離20MA乖離 (%)": round(item["dist_ma20"], 1),
                "布林壓縮寬度 (%)": round(item["bb_width"], 1),
                "CMF 主力吃貨": round(item["cmf20"], 3),
                "RVOL 量比": round(item["rvol"], 2),
                "現價 ($)": round(item["curr_p"], 2),
                "單日漲跌 (%)": round(item["pct_chg"], 2),
                "近20日走勢": item["trend_20d"],
                "ATR 停損價 ($)": round(item["stop_loss"], 2),
                "風控建議股數": item["shares"],
                "下次財報日": f_info["earnings_str"]
            })
            
    return pd.DataFrame(final_rows), raw_histories, price_lookup, atr_stop_lookup

with st.spinner("🎯 正在掃描全市場：尋找「布林壓縮蓄勢、主力暗池背離吃貨、貼近均線剛起漲」之潛伏標的..."):
    df_scan, histories, live_prices, live_stops = run_sniper_screener(
        MARKET_UNIVERSE, user_custom_list, portfolio_tickers,
        state["auto_pick_count"], state["capital"], state["risk_pct"], state["atr_mult"], state.get("strategy_mode", "")
    )

# ==========================================
# 模組二：我的持倉部位與預算管理中心 (綁定 6位數通行碼)
# ==========================================
st.subheader(f"💼 模組二：我的持倉倉位與預算損益管理（已綁定記憶碼：`{st.session_state.current_pin}`）")

col_port_edit, col_port_summary = st.columns([1.4, 2.6])

with col_port_edit:
    st.markdown("##### ✏️ 編輯我的持倉清單")
    port_df_input = pd.DataFrame(state["portfolio"]) if state["portfolio"] else pd.DataFrame(columns=["Ticker", "Shares", "Avg_Cost"])
    edited_port_df = st.data_editor(
        port_df_input, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "Ticker": st.column_config.TextColumn("股票代號", required=True),
            "Shares": st.column_config.NumberColumn("持有股數", min_value=0.0, step=1.0, required=True),
            "Avg_Cost": st.column_config.NumberColumn("平均買進成本 ($)", min_value=0.01, step=0.5, required=True)
        }
    )
    cleaned_port = []
    for _, r in edited_port_df.iterrows():
        t_val = str(r.get("Ticker", "")).strip().upper()
        s_val = float(r.get("Shares", 0) or 0)
        c_val = float(r.get("Avg_Cost", 0) or 0)
        if t_val and s_val > 0:
            cleaned_port.append({"Ticker": t_val, "Shares": s_val, "Avg_Cost": c_val})
    if cleaned_port != state["portfolio"]:
        state["portfolio"] = cleaned_port
        sync_state()
        st.rerun()

with col_port_summary:
    st.markdown("##### 📊 倉位即時損益與 ATR 停損診斷")
    port_eval_rows = []
    total_market_val, total_cost_val = 0.0, 0.0
    
    for item in state["portfolio"]:
        sym, shares, cost = item["Ticker"], item["Shares"], item["Avg_Cost"]
        curr_p = live_prices.get(sym, cost)
        stop_p = live_stops.get(sym, curr_p * 0.92)
        
        mkt_val, cost_val = shares * curr_p, shares * cost
        pnl_usd = mkt_val - cost_val
        pnl_pct = ((curr_p - cost) / cost) * 100 if cost > 0 else 0.0
        total_market_val += mkt_val
        total_cost_val += cost_val
        
        action_hint = "🚨 觸及 ATR 停損！建議執行風控" if curr_p <= stop_p else ("💰 獲利豐厚，可上移停損鎖利" if pnl_pct >= 15 else "✅ 正常續抱 (守穩停損線之上)")
        port_eval_rows.append({
            "代號": sym, "股數": shares, "成本價": round(cost, 2), "現價": round(curr_p, 2),
            "持倉市值 ($)": round(mkt_val, 2), "未實現損益 ($)": round(pnl_usd, 2),
            "報酬率 (%)": round(pnl_pct, 2), "ATR 防守停損價": round(stop_p, 2), "倉位診斷": action_hint
        })
        
    remaining_cash = state["capital"] - total_cost_val
    total_equity = remaining_cash + total_market_val
    total_pnl = total_market_val - total_cost_val
    pos_ratio = (total_market_val / total_equity * 100) if total_equity > 0 else 0.0
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("總資產淨值 (含未實現)", f"${total_equity:,.2f}", f"{total_pnl:+,.2f} USD")
    m2.metric("目前持倉總市值", f"${total_market_val:,.2f}", f"水位佔比 {pos_ratio:.1f}%", delta_color="off")
    m3.metric("剩餘可用現金預算", f"${remaining_cash:,.2f}")
    m4.metric("設定總預算基準", f"${state['capital']:,.0f}")
    
    if port_eval_rows:
        st.dataframe(pd.DataFrame(port_eval_rows), use_container_width=True, hide_index=True)

st.divider()

# ==========================================
# 模組三：起漲前潛伏狙擊雷達總表
# ==========================================
st.subheader("📡 模組三：AI「起漲前夕潛伏狙擊」雷達總表（拒絕追高！）")

with st.expander("📖 點此查看：如何利用這張表在「大漲爆發前」提前卡位？（實戰秘訣）"):
    st.markdown("""
    * **為什麼這張表能幫你買在起漲前？** 傳統選股只看誰漲最多，結果買進去就套在山頂。本系統改抓**「還沒大漲，但主力已經偷偷買好」**的四大先行指標：
      1. **🎯 口袋支點剛點火（最推薦！）**：股價在月線附近整理完畢，今天出現第一根放量紅 K（成交量大於過去10天所有黑K量），且**離 20MA 乖離率小於 5%**，這是起漲的第一發信號彈！
      2. **🔋 VCP 波動壓縮蓄勢**：看表中的**「布林壓縮寬度 (%)」**，數字越小（例如 `< 14%`）代表股價上下震幅被壓縮到極致，同時 `CMF > 0.05` 代表主力在裡面鎖碼，隨時準備向上噴出。
      3. **🐳 主力橫盤暗池吃貨**：過去兩週股價明明沒什麼漲，但 **CMF 主力吃貨指標卻高達 `0.10` 以上**，或 **OBV 能量潮率先創高**，代表大戶趁沒人注意時正在底部大舉收購籌碼。
      4. **⚓ 回測均線黃金支撐**：看表中的**「離20MA乖離 (%)」**，當數值落在 **`-2.0% ~ +3.0%`** 之間時，代表股價剛好踩在月線支撐上，這時候買進成本最低、離停損點最近，安全邊際最高！
    """)

col_f1, col_f2, col_f3 = st.columns([1.2, 1.5, 2.3])
with col_f1:
    if st.button("🔄 立即重新掃描潛伏買點", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
with col_f2:
    hide_overextended = st.checkbox("🛡️ 自動隱藏「已漲高(乖離>8%)」標的", value=True, help="勾選後會直接濾掉已經大漲遠離月線的股票，確保你絕對不會追高！")
with col_f3:
    only_stealth_inflow = st.checkbox("🐳 只顯示「主力暗池吃貨中 (CMF > 0)」", value=False)

if not df_scan.empty:
    df_show = df_scan.copy()
    if hide_overextended:
        df_show = df_show[(df_show["離20MA乖離 (%)"] <= 8.0) | (df_show["入選來源"].str.contains("持倉|自選"))]
    if only_stealth_inflow:
        df_show = df_show[df_show["CMF 主力吃貨"] > 0]
        
    st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "潛伏狙擊分": st.column_config.ProgressColumn(
                "潛伏爆發分 (0-100)", format="%d 分", min_value=0, max_value=100,
                help="分數越高代表：越貼近均線支撐(未漲高) + 布林通道越壓縮 + CMF主力暗池吃貨越強！"
            ),
            "離20MA乖離 (%)": st.column_config.NumberColumn(
                "離月線距離 (%)", format="%+.1f%%",
                help="🎯 黃金潛伏區為 -2% ~ +3.5%（剛起漲或回測支撐）；若 > +8% 代表短線已經漲太多，切勿追高！"
            ),
            "布林壓縮寬度 (%)": st.column_config.NumberColumn(
                "布林壓縮率 (%)", format="%.1f%%",
                help="🔋 數值越小（尤其 <14%）代表波動率極度收斂、彈簧壓到底，即將變盤大爆發！"
            ),
            "CMF 主力吃貨": st.column_config.NumberColumn("CMF 暗池籌碼", help=">0.08 代表主力資金明顯在底部吸籌"),
            "近20日走勢": st.column_config.LineChartColumn("近20日走勢"),
            "單日漲跌 (%)": st.column_config.NumberColumn("今日漲跌", format="%+.2f%%")
        }
    )

st.divider()

# ==========================================
# 模組四：布林壓縮通道 ＋ OBV 領先指標 ＋ CMF 觸控看盤室
# ==========================================
st.subheader("📊 模組四：爆發前夕 K 線解剖室（含布林壓縮通道 ＆ OBV 能量潮領先指標）")
st.caption("💡 看圖秘訣：觀察主圖的**「紫色虛線（布林通道上下軌）」是否正在收窄壓縮**，並對照最下方**「黃色 OBV 能量潮線」是否已經比股價提早創高（主力偷吃貨鐵證）**！")

if not df_scan.empty:
    available_tickers = df_scan["代號"].tolist()
    default_idx = available_tickers.index(state["last_selected_ticker"]) if state["last_selected_ticker"] in available_tickers else 0
    
    c_sel1, c_sel2 = st.columns([1, 2])
    with c_sel1:
        selected_ticker = st.selectbox("🎯 選擇要解剖的標的：", available_tickers, index=default_idx)
        if selected_ticker != state["last_selected_ticker"]:
            state["last_selected_ticker"] = selected_ticker
            sync_state()
    with c_sel2:
        timeframe = st.radio(
            "🕒 選擇 K 線週期：",
            ["📅 波段潛伏日 K 線 (含布林壓縮軌 + 均線 + CMF & OBV 籌碼)", "⚡ 盤中 5 分鐘 K 線 (抓當日突破瞬間)", "⚡ 盤中 15 分鐘 K 線 (短波段拐點)"],
            horizontal=True
        )
        
    touch_chart_config = {
        'scrollZoom': True,
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['select2d', 'lasso2d']
    }
        
    if "波段潛伏日 K" in timeframe:
        df_plot = histories[selected_ticker].tail(140).copy()
        df_plot['MA20'] = df_plot['Close'].rolling(20).mean()
        df_plot['MA50'] = df_plot['Close'].rolling(50).mean()
        std20 = df_plot['Close'].rolling(20).std()
        df_plot['BB_Upper'] = df_plot['MA20'] + 2 * std20
        df_plot['BB_Lower'] = df_plot['MA20'] - 2 * std20
        
        mfm = ((df_plot['Close'] - df_plot['Low']) - (df_plot['High'] - df_plot['Close'])) / (df_plot['High'] - df_plot['Low'] + 1e-9)
        df_plot['CMF'] = (mfm * df_plot['Volume']).rolling(20).sum() / (df_plot['Volume'].rolling(20).sum() + 1e-9)
        df_plot['OBV'] = (df_plot['Volume'] * df_plot['Close'].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))).cumsum()
        
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.55, 0.22, 0.23],
            subplot_titles=(
                f"{selected_ticker} 日 K 線 ＋ 布林壓縮通道 (紫虛線) ＋ 20MA(橘) / 50MA(藍)",
                "CMF 主力暗池資金流 (綠柱＝主力吃貨 / 紅柱＝主力出貨)",
                "OBV 能量潮累積線 (黃線若比股價提早創高＝爆發前主力鎖碼)"
            )
        )
        # 布林上下軌與 K 線
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Upper'], line=dict(color='rgba(171, 71, 188, 0.6)', width=1, dash='dot'), name='布林上軌'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Lower'], line=dict(color='rgba(171, 71, 188, 0.6)', width=1, dash='dot'), fill='tonexty', fillcolor='rgba(171, 71, 188, 0.07)', name='布林壓縮區'), row=1, col=1)
        fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'], name="日K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA20'], line=dict(color='#FFA726', width=1.8), name='20MA (月線支撐)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA50'], line=dict(color='#29B6F6', width=1.8), name='50MA (季線支撐)'), row=1, col=1)
        
        # CMF
        cmf_colors = ['#26a69a' if v >= 0 else '#ef5350' for v in df_plot['CMF']]
        fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['CMF'], marker_color=cmf_colors, name="CMF 籌碼"), row=2, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)
        
        # OBV
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['OBV'], line=dict(color='#FFEE58', width=2), name="OBV 能量潮"), row=3, col=1)
        
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        fig.update_layout(height=750, xaxis_rangeslider_visible=False, template="plotly_dark", dragmode="pan")
        fig.update_yaxes(fixedrange=False)
        st.plotly_chart(fig, use_container_width=True, config=touch_chart_config)
    else:
        interval_str = "5m" if "5 分鐘" in timeframe else "15m"
        period_str = "5d" if interval_str == "5m" else "1mo"
        with st.spinner(f"正在載入 {selected_ticker} 的 {interval_str} 盤中即時 K 線..."):
            df_intra = yf.download(selected_ticker, period=period_str, interval=interval_str, progress=False)
            if isinstance(df_intra.columns, pd.MultiIndex):
                df_intra.columns = df_intra.columns.get_level_values(0)
            df_intra = df_intra.dropna().tail(150).copy()
            
            df_intra['EMA20'] = df_intra['Close'].ewm(span=20).mean()
            df_intra['Date'] = df_intra.index.date
            df_intra['TypPrice'] = (df_intra['High'] + df_intra['Low'] + df_intra['Close']) / 3
            df_intra['VP'] = df_intra['TypPrice'] * df_intra['Volume']
            df_intra['VWAP'] = df_intra.groupby('Date')['VP'].cumsum() / (df_intra.groupby('Date')['Volume'].cumsum() + 1e-9)
            
            time_labels = df_intra.index.strftime('%m-%d %H:%M')
            fig_intra = make_subplots(
                rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.72, 0.28],
                subplot_titles=(f"{selected_ticker} 盤中 {interval_str} K 線 (20EMA 與 每日重置機構 VWAP)", "盤中分時成交量")
            )
            fig_intra.add_trace(go.Candlestick(x=time_labels, open=df_intra['Open'], high=df_intra['High'], low=df_intra['Low'], close=df_intra['Close'], name=f"{interval_str} K線"), row=1, col=1)
            fig_intra.add_trace(go.Scatter(x=time_labels, y=df_intra['EMA20'], line=dict(color='#FFA726', width=1.5), name='20 EMA'), row=1, col=1)
            fig_intra.add_trace(go.Scatter(x=time_labels, y=df_intra['VWAP'], line=dict(color='#FFEE58', width=1.5, dash='dash'), name='當日 VWAP'), row=1, col=1)
            
            v_colors = ['#ef5350' if c < o else '#26a69a' for c, o in zip(df_intra['Close'], df_intra['Open'])]
            fig_intra.add_trace(go.Bar(x=time_labels, y=df_intra['Volume'], marker_color=v_colors, name="分時量"), row=2, col=1)
            
            fig_intra.update_layout(height=620, xaxis_rangeslider_visible=False, template="plotly_dark", dragmode="pan")
            fig_intra.update_yaxes(fixedrange=False)
            st.plotly_chart(fig_intra, use_container_width=True, config=touch_chart_config)

st.divider()

# ==========================================
# 模組五：全中文個股財報基本面 ＆ 華爾街外電中英雙語快訊
# ==========================================
st.subheader(f"📰 模組五：{selected_ticker} 財報基本面體質 ＆ 華爾街即時新聞 (自動繁中翻譯)")

col_fund, col_news = st.columns([1.2, 1.8])

with col_fund:
    st.markdown(f"#### 🏦 {selected_ticker} 財報與機構目標價診斷")
    f_data = get_earnings_and_fundamentals(selected_ticker)
    curr_price_sel = float(histories[selected_ticker]['Close'].iloc[-1])
    
    f1, f2 = st.columns(2)
    f1.metric("📅 下次財報公布日", f_data["earnings_str"])
    if f_data["target_price"]:
        upside = ((f_data["target_price"] - curr_price_sel) / curr_price_sel) * 100
        f2.metric("🎯 華爾街平均目標價", f"${f_data['target_price']:.2f}", f"{upside:+.1f}% 潛在空間")
    else:
        f2.metric("🎯 華爾街平均目標價", "暫無數據")
        
    f3, f4 = st.columns(2)
    f3.metric("📊 預估本益比 (Forward P/E)", f"{f_data['pe_forward']:.1f} 倍" if f_data["pe_forward"] else "暫無數據")
    f4.metric("⭐ 機構分析師共識評級", f_data["recommendation_zh"])
    
    f5, f6 = st.columns(2)
    f5.metric("📈 營收年增率 (YoY)", f"{f_data['rev_growth']*100:+.1f}%" if f_data["rev_growth"] else "暫無數據")
    f6.metric("💰 企業淨利率", f"{f_data['profit_margin']*100:.1f}%" if f_data["profit_margin"] else "暫無數據")

with col_news:
    news_tab1, news_tab2 = st.tabs([f"{selected_ticker} 最新外電 (中英對照)", "華爾街大盤總經頭條 (中英對照)"])
    with news_tab1:
        ticker_news = fetch_zh_wallstreet_news(selected_ticker, is_macro=False)
        for n in ticker_news:
            st.markdown(
                f"**• [{n['title_zh']}]({n['link']})**  \n"
                f"<span style='color:#9e9e9e;font-size:12px;'>🇺🇸 原題：{n['title_en']}</span>  \n"
                f"<span style='color:gray;font-size:12px;'>來源：{n['publisher']} ｜ {n['time']}</span>",
                unsafe_allow_html=True
            )
    with news_tab2:
        macro_news = fetch_zh_wallstreet_news("SPY", is_macro=True)
        for n in macro_news:
            st.markdown(
                f"**• [{n['title_zh']}]({n['link']})**  \n"
                f"<span style='color:#9e9e9e;font-size:12px;'>🇺🇸 原題：{n['title_en']}</span>  \n"
                f"<span style='color:gray;font-size:12px;'>來源：{n['publisher']} ｜{n['time']}</span>",
                unsafe_allow_html=True
            )

if auto_refresh:
    time.sleep(refresh_sec)
    st.cache_data.clear()
    st.rerun()
