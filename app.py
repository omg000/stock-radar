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

# 1. 網頁基本設定 (無花俏符號，專業終端風格)
st.set_page_config(page_title="量化潛伏狙擊系統 6.0 (美股/台股雙市場)", layout="wide")

# ==========================================
# 6位數通行碼 (PIN) 記憶保險箱引擎
# ==========================================
VAULT_FILE = "pin_vault_v6.json"

DEFAULT_STATE = {
    "market": "美股 (US)",
    "strategy_mode": "潛伏起漲狙擊 (爆發前佈局/不追高)",
    "auto_pick_count": 15,
    "us_capital": 10000.0,
    "us_watchlist": "NVDA, TSLA, PLTR, AMD",
    "us_last_ticker": "NVDA",
    "us_portfolio": [
        {"Ticker": "NVDA", "Shares": 10.0, "Avg_Cost": 120.0}
    ],
    "tw_capital": 300000.0,
    "tw_watchlist": "0050, 2330, 3037, 2317",
    "tw_last_ticker": "2330.TW",
    "tw_portfolio": [
        {"Ticker": "0050.TW", "Shares": 1000.0, "Avg_Cost": 180.0}
    ],
    "risk_pct": 1.5,
    "atr_mult": 2.0
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
# 美股與台股核心母體池 ＆ 台股名稱對照表
# ==========================================
US_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "NFLX",
    "AMD", "AVGO", "TSM", "MU", "ARM", "SMCI", "MRVL", "ANET", "VRT", "DELL",
    "PLTR", "CRWD", "PANW", "NOW", "SNOW", "ORCL", "CRM", "SHOP", "APP", "IOT",
    "JPM", "GS", "V", "MA", "AXP", "COIN", "HOOD", "SOFI", "MSTR",
    "LLY", "ISRG", "UNH", "COST", "WMT", "UBER", "CAT", "GE", "XOM", "CEG", "VST"
]

TW_NAME_MAP = {
    "0050.TW": "元大台灣50", "0056.TW": "元大高股息", "00878.TW": "國泰永續高股息",
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2382.TW": "廣達", "3231.TW": "緯創", "6669.TW": "緯穎", "2357.TW": "華碩",
    "3037.TW": "欣興", "3017.TW": "奇鋐", "3324.TW": "雙鴻", "2345.TW": "智邦",
    "3034.TW": "聯詠", "2379.TW": "瑞昱", "3443.TW": "創意", "3661.TW": "世芯-KY",
    "2303.TW": "聯電", "3711.TW": "日月光投控", "2408.TW": "南亞科", "2344.TW": "華邦電",
    "2603.TW": "長榮", "2609.TW": "陽明", "2615.TW": "萬海", "2618.TW": "長榮航",
    "1519.TW": "華城", "1513.TW": "中興電", "1503.TW": "士電", "1605.TW": "華新",
    "2881.TW": "富邦金", "2882.TW": "國泰金", "2891.TW": "中信金", "2886.TW": "兆豐金",
    "1216.TW": "統一", "2912.TW": "統一超", "2002.TW": "中鋼", "1101.TW": "台泥",
    "3008.TW": "大立光", "2327.TW": "國巨", "2395.TW": "研華", "6446.TW": "藥華藥"
}
TW_UNIVERSE = list(TW_NAME_MAP.keys())

def normalize_tw_ticker(raw_str):
    t = raw_str.strip().upper()
    if not t:
        return ""
    if not t.endswith(".TW") and not t.endswith(".TWO") and not t.startswith("^"):
        return f"{t}.TW"
    return t

def format_symbol_display(sym, is_tw):
    if is_tw and sym in TW_NAME_MAP:
        clean_code = sym.replace(".TW", "")
        return f"{clean_code} {TW_NAME_MAP[sym]}"
    return sym

# ==========================================
# 側邊欄：市場切換、6位數記憶碼、策略與風控
# ==========================================
st.sidebar.header("系統核心設定")

market_options = ["美股 (US)", "台股 (TW)"]
curr_mkt_idx = 0 if state.get("market", "美股 (US)") == "美股 (US)" else 1
selected_market = st.sidebar.radio("選擇交易市場：", market_options, index=curr_mkt_idx, horizontal=True)
is_tw_market = (selected_market == "台股 (TW)")

if selected_market != state.get("market"):
    state["market"] = selected_market
    sync_state()
    st.rerun()

st.sidebar.subheader("6位數專屬記憶通行碼")
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
                st.sidebar.success(f"🟢 已載入 [{pin_input}]")
            else:
                save_to_vault(pin_input, st.session_state.user_state)
                st.sidebar.success(f"🟢 已建立 [{pin_input}]")
            st.rerun()

st.sidebar.caption(f"目前綁定記憶碼：`{st.session_state.current_pin}` (自動存檔)")
st.sidebar.divider()

mode_options = [
    "潛伏起漲狙擊 (爆發前佈局/不追高)",
    "右側動能突破 (追隨已爆發強勢股)"
]
curr_mode_idx = 0 if "潛伏" in state.get("strategy_mode", "") else 1
new_mode = st.sidebar.radio("選股演算法邏輯：", mode_options, index=curr_mode_idx)

auto_refresh = st.sidebar.toggle("開啟盤中自動更新", value=False)
refresh_sec = st.sidebar.selectbox("自動更新頻率 (秒)", [60, 180, 300], index=1)

st.sidebar.subheader("系統海選與自選清單")
new_auto_count = st.sidebar.slider("系統自動海選標的數量", min_value=5, max_value=25, value=int(state["auto_pick_count"]), step=1)

if is_tw_market:
    watch_label = "台股自選清單 (輸入代號即可，如 0050, 2330)"
    curr_watch_val = state.get("tw_watchlist", "0050, 2330, 3037")
    cap_label = "總投資預算 (新台幣 TWD)"
    curr_cap_val = float(state.get("tw_capital", 300000.0))
    cap_step = 10000.0
else:
    watch_label = "美股自選清單 (逗號分隔，如 NVDA, TSLA)"
    curr_watch_val = state.get("us_watchlist", "NVDA, TSLA, PLTR")
    cap_label = "總投資預算 (美元 USD)"
    curr_cap_val = float(state.get("us_capital", 10000.0))
    cap_step = 500.0

new_watchlist = st.sidebar.text_area(watch_label, value=curr_watch_val, height=70)

st.sidebar.subheader("預算與量化風控參數")
new_capital = st.sidebar.number_input(cap_label, min_value=500.0, value=curr_cap_val, step=cap_step)
new_risk = st.sidebar.slider("單筆最大承受虧損 (%)", 0.5, 5.0, float(state["risk_pct"]), 0.5)
new_atr = st.sidebar.slider("ATR 停損寬度 (倍)", 1.0, 4.0, float(state["atr_mult"]), 0.5)

# 檢查變更並儲存
changed = False
if new_mode != state.get("strategy_mode") or new_auto_count != state["auto_pick_count"] or new_risk != state["risk_pct"] or new_atr != state["atr_mult"]:
    state["strategy_mode"] = new_mode
    state["auto_pick_count"] = new_auto_count
    state["risk_pct"] = new_risk
    state["atr_mult"] = new_atr
    changed = True

if is_tw_market:
    if new_watchlist != state.get("tw_watchlist") or new_capital != state.get("tw_capital"):
        state["tw_watchlist"] = new_watchlist
        state["tw_capital"] = new_capital
        changed = True
else:
    if new_watchlist != state.get("us_watchlist") or new_capital != state.get("us_capital"):
        state["us_watchlist"] = new_watchlist
        state["us_capital"] = new_capital
        changed = True

if changed:
    sync_state()

# ==========================================
# 美股 / 台股 開休市狀態自動偵測器
# ==========================================
def get_market_status_banner(is_tw):
    now_et = datetime.now(ZoneInfo("America/New_York"))
    now_tw = datetime.now(ZoneInfo("Asia/Taipei"))
    
    if is_tw:
        weekday = now_tw.weekday()
        curr_t = now_tw.time()
        open_t, close_t = dt_time(9, 0), dt_time(13, 30)
        if weekday >= 5:
            badge = "🔴 台股休市中 (週末休市)"
            detail = "目前為休市時段，顯示最新一個交易日之收盤與籌碼數據，適合篩選下週潛伏標的。"
        elif open_t <= curr_t < close_t:
            close_dt = datetime.combine(now_tw.date(), close_t, tzinfo=ZoneInfo("Asia/Taipei"))
            rem = close_dt - now_tw
            hrs, rem_s = divmod(int(rem.total_seconds()), 3600)
            mins = rem_s // 60
            badge = f"🟢 台股盤中交易進行中 ｜ 距離 13:30 收盤剩餘 {hrs}小時 {mins}分"
            detail = "台股盤中即時報價與分時 K 線運作中。"
        elif dt_time(8, 30) <= curr_t < open_t:
            badge = "🟡 台股盤前試撮階段 (08:30 - 09:00)"
            detail = "即將開盤，可觀察美股昨夜收盤表現與台股期貨動向。"
        else:
            badge = "🔴 台股已收盤 (盤後休市時段)"
            detail = "正規盤已收盤，系統已完成今日籌碼與均線結算。"
    else:
        weekday = now_et.weekday()
        curr_t = now_et.time()
        open_t, close_t, pre_t, after_t = dt_time(9, 30), dt_time(16, 0), dt_time(4, 0), dt_time(20, 0)
        if weekday >= 5:
            badge = "🔴 美股休市中 (週末休市)"
            detail = "目前為休市時段，顯示最新一個交易日收盤數據，適合篩選下週壓縮蓄勢之潛伏標的。"
        elif open_t <= curr_t < close_t:
            close_dt = datetime.combine(now_et.date(), close_t, tzinfo=ZoneInfo("America/New_York"))
            rem = close_dt - now_et
            hrs, rem_s = divmod(int(rem.total_seconds()), 3600)
            mins = rem_s // 60
            badge = f"🟢 美股正規盤交易中 (Market OPEN) ｜ 距離收盤剩餘 {hrs}小時 {mins}分"
            detail = "美股盤中即時報價與起漲拐點偵測運作中。"
        elif pre_t <= curr_t < open_t:
            open_dt = datetime.combine(now_et.date(), open_t, tzinfo=ZoneInfo("America/New_York"))
            rem = open_dt - now_et
            hrs, rem_s = divmod(int(rem.total_seconds()), 3600)
            mins = rem_s // 60
            badge = f"🟡 美股盤前交易時段 (Pre-Market) ｜ 距離正式開盤剩餘 {hrs}小時 {mins}分"
            detail = "即將開盤，可留意下方總經政策與市場走向新聞。"
        elif close_t <= curr_t < after_t:
            badge = "🟡 美股盤後電子盤交易時段 (After-Hours)"
            detail = "正規盤已收盤，目前為盤後交易時段。"
        else:
            badge = "🔴 美股夜盤休市中"
            detail = "等待美東時間 04:00 盤前開市。"
            
    clock_str = f"台灣時間: {now_tw.strftime('%Y-%m-%d %H:%M')} ｜ 美東時間: {now_et.strftime('%Y-%m-%d %H:%M')} ET"
    return badge, detail, clock_str

mkt_title = "台股 (TW)" if is_tw_market else "美股 (US)"
st.title(f"量化潛伏狙擊與追蹤系統 6.0 — {mkt_title}")
st.caption("核心機制：VCP 波動壓縮蓄勢 ｜ 主力橫盤暗池吃貨 ｜ 均線支撐買點 ｜ 總經與地緣政治情緒追蹤")
mkt_badge, mkt_detail, mkt_clock = get_market_status_banner(is_tw_market)
st.info(f"**{mkt_badge}** \n{mkt_clock} ｜ {mkt_detail}")

# ==========================================
# 輔助函數：100% 原生繁體中文重大新聞與情緒判讀引擎
# ==========================================
POS_KEYWORDS = ["降息", "利多", "大漲", "創高", "優於預期", "買進", "調升", "反彈", "突破", "成長", "強勁", "擴產", "獲利", "看旺", "入列"]
NEG_KEYWORDS = ["升息", "通膨", "暴跌", "重挫", "利空", "低於預期", "關稅", "禁令", "制裁", "衰退", "賣出", "調降", "砍單", "下修", "恐慌", "戰爭", "衝突"]

def analyze_headline_sentiment(title_text):
    pos_hits = sum(1 for k in POS_KEYWORDS if k in title_text)
    neg_hits = sum(1 for k in NEG_KEYWORDS if k in title_text)
    if pos_hits > neg_hits:
        return "🟢 偏多利多"
    elif neg_hits > pos_hits:
        return "🔴 偏空警戒"
    return "🟡 中性觀察"

@st.cache_data(ttl=300)
def fetch_native_zh_news(search_query):
    """直接向 Google News 台灣繁體中文財經資料庫抓取 100% 繁中新聞，徹底解決翻譯失敗問題"""
    items = []
    try:
        encoded_q = urllib.parse.quote(search_query)
        url = f"https://news.google.com/rss/search?q={encoded_q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=6) as response:
            root = ET.fromstring(response.read())
            for item in root.findall('.//item')[:8]:
                raw_title = item.find('title').text if item.find('title') is not None else ""
                clean_title = raw_title.rsplit(" - ", 1)[0] if " - " in raw_title else raw_title
                link = item.find('link').text if item.find('link') is not None else ""
                source = item.find('source').text if item.find('source') is not None else "財經快訊"
                pub_date = item.find('pubDate').text[:16] if item.find('pubDate') is not None else ""
                if clean_title:
                    sentiment_tag = analyze_headline_sentiment(clean_title)
                    items.append({
                        "sentiment": sentiment_tag,
                        "title": clean_title,
                        "link": link,
                        "source": source,
                        "time": pub_date
                    })
    except Exception:
        pass
    return items

RATING_MAP_ZH = {
    "STRONG_BUY": "🟢 強力買進", "BUY": "🟢 買進", "HOLD": "🟡 觀望持有",
    "UNDERPERFORM": "🔴 表現落後", "SELL": "🔴 賣出", "NONE": "暫無評級", "N/A": "暫無評級"
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
                    res["earnings_str"] = f"🔴 {e_date.strftime('%m/%d')} ({days_diff}天後)"
                elif days_diff > 14:
                    res["earnings_str"] = f"🟢 {e_date.strftime('%m/%d')} ({days_diff}天後)"
                else:
                    res["earnings_str"] = f"已公布 ({e_date.strftime('%m/%d')})"
                    
        info = tk.info
        if isinstance(info, dict):
            res["pe_forward"] = info.get("forwardPE") or info.get("trailingPE")
            res["rev_growth"] = info.get("revenueGrowth")
            res["profit_margin"] = info.get("profitMargins")
            res["target_price"] = info.get("targetMeanPrice")
            raw_rec = str(info.get("recommendationKey", "N/A")).upper()
            res["recommendation_zh"] = RATING_MAP_ZH.get(raw_rec, raw_rec)
    except Exception:
        pass
    return res

# ==========================================
# 模組一：全方位宏觀與市場情緒中心 (支援美股/台股切換)
# ==========================================
st.subheader("模組一：市場情緒溫度計與大盤宏觀雷達")

@st.cache_data(ttl=120)
def get_macro_dashboard():
    symbols = ["^VIX", "SPY", "QQQ", "^SOX", "^TNX", "^TWII", "0050.TW", "2330.TW"]
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
        if vix < 15:
            vix_status = "🟢 極度樂觀 (勿追高/找低位階潛伏)"
        elif vix < 20:
            vix_status = "🟢 穩定偏多 (適合佈局壓縮突破)"
        elif vix < 30:
            vix_status = "🟡 警戒震盪 (逢回測均線買黑不買紅)"
        else:
            vix_status = "🔴 極度恐慌 (嚴控風險/等待底部背離)"
            
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta", value=vix,
            delta={'reference': vix - vix_diff, 'increasing': {'color': "#ef5350"}, 'decreasing': {'color': "#26a69a"}},
            title={'text': f"<b>VIX 市場恐慌指數</b><br><span style='font-size:13px;color:gray'>{vix_status}</span>"},
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
        c4, c5, c6 = st.columns(3)
        if is_tw_market:
            twii, etf0050, tsmc, sox, tnx = m_data["^TWII"], m_data["0050.TW"], m_data["2330.TW"], m_data["^SOX"], m_data["^TNX"]
            c1.metric("台灣加權指數 (^TWII)", f"{twii['curr']:,.0f}", f"{twii['chg_pct']:+.2f}%")
            c2.metric("元大台灣50 (0050)", f"{etf0050['curr']:.2f}", f"{etf0050['chg_pct']:+.2f}%")
            c3.metric("台積電 (2330)", f"{tsmc['curr']:.1f}", f"{tsmc['chg_pct']:+.2f}%")
            c4.metric("美股費城半導體 (^SOX)", f"{sox['curr']:,.1f}", f"{sox['chg_pct']:+.2f}%", help="台股電子股開盤最重要領先指標")
            c5.metric("10年期美債殖利率 (^TNX)", f"{tnx['curr']:.2f}%", f"{tnx['chg_abs']:+.2f}", delta_color="inverse")
            main_idx = twii
        else:
            spy, qqq, sox, tsmc, tnx = m_data["SPY"], m_data["QQQ"], m_data["^SOX"], m_data["2330.TW"], m_data["^TNX"]
            c1.metric("標普 500 指數 (SPY)", f"${spy['curr']:.2f}", f"{spy['chg_pct']:+.2f}%")
            c2.metric("納斯達克 100 (QQQ)", f"${qqq['curr']:.2f}", f"{qqq['chg_pct']:+.2f}%")
            c3.metric("費城半導體 (^SOX)", f"{sox['curr']:,.1f}", f"{sox['chg_pct']:+.2f}%")
            c4.metric("台灣加權指數 (^TWII)", f"{m_data['^TWII']['curr']:,.0f}", f"{m_data['^TWII']['chg_pct']:+.2f}%")
            c5.metric("10年期美債殖利率 (^TNX)", f"{tnx['curr']:.2f}%", f"{tnx['chg_abs']:+.2f}", delta_color="inverse")
            main_idx = spy
            
        with c6:
            st.markdown("##### 盤勢與潛伏時機診斷")
            if vix < 20 and main_idx['curr'] > main_idx['ma20']:
                st.success("**🟢 綠燈：多頭順風環境**\n\n大盤站穩月線且恐慌指數低，適合鎖定下方「壓縮蓄勢」或「口袋支點剛起漲」標的佈局。")
            elif vix >= 25 or main_idx['curr'] < main_idx['ma50']:
                st.error("**🔴 紅燈：空頭風險警戒**\n\n大盤跌破季線或恐慌飆升，建議拉高現金比例，嚴格執行停損。")
            else:
                st.warning("**🟡 黃燈：區間震盪整理**\n\n指數橫盤震盪，切忌追高，專挑「回測均線支撐」且主力資金為正的標的。")
except Exception as e:
    st.warning(f"正在同步大盤宏觀數據... ({e})")

st.divider()

# ==========================================
# 模組二：影響市場情緒與走向之重大中文財經新聞中心
# ==========================================
st.subheader("模組二：影響市場情緒與走向之重大財經新聞 (100% 繁體中文情報源)")
st.caption("系統自動從四大宏觀與產業維度抓取最新繁體中文外電與財經快訊，並根據關鍵字自動標記「🟢 偏多利多 / 🟡 中性觀察 / 🔴 偏空警戒」情緒燈號。")

news_tabs = st.tabs([
    "1. 聯準會與總經通膨動向",
    "2. 地緣政治與關稅政策",
    "3. AI 供應鏈與科技巨頭風向",
    "4. 台股與外資法人焦點"
])

macro_queries = [
    "聯準會 降息 OR 通膨 CPI OR 非農 OR 美債殖利率 美股",
    "川普 關稅 OR 晶片禁令 OR 地緣政治 美股 台股",
    "輝達 NVDA OR 台積電 CoWoS OR AI伺服器 財報 營收",
    "台股 外資 買賣超 OR 台積電 法說會 OR 0050"
]

for tab_obj, q_str in zip(news_tabs, macro_queries):
    with tab_obj:
        news_list = fetch_native_zh_news(q_str)
        if news_list:
            bull_cnt = sum(1 for n in news_list if "🟢" in n["sentiment"])
            bear_cnt = sum(1 for n in news_list if "🔴" in n["sentiment"])
            if bull_cnt > bear_cnt:
                st.markdown(f"**本頻道新聞情緒溫度：🟢 利多消息佔優** (利多 {bull_cnt} 則 / 利空 {bear_cnt} 則)")
            elif bear_cnt > bull_cnt:
                st.markdown(f"**本頻道新聞情緒溫度：🔴 利空與警戒消息佔優** (利多 {bull_cnt} 則 / 利空 {bear_cnt} 則)")
            else:
                st.markdown(f"**本頻道新聞情緒溫度：🟡 多空消息均衡** (利多 {bull_cnt} 則 / 利空 {bear_cnt} 則)")
                
            col_n1, col_n2 = st.columns(2)
            for idx, n in enumerate(news_list):
                target_col = col_n1 if idx % 2 == 0 else col_n2
                target_col.markdown(
                    f"**{n['sentiment']} ｜ [{n['title']}]({n['link']})**  \n"
                    f"<span style='color:gray;font-size:12px;'>媒體來源：{n['source']} ｜ 時間：{n['time']}</span>",
                    unsafe_allow_html=True
                )
        else:
            st.write("目前暫無相關新聞。")

st.divider()

# ==========================================
# 全自動海選引擎 (美股 / 台股雙軌支援)
# ==========================================
if is_tw_market:
    active_universe = TW_UNIVERSE
    active_custom = [normalize_tw_ticker(t) for t in state.get("tw_watchlist", "").split(",") if t.strip()]
    active_port_list = state.get("tw_portfolio", [])
    active_port_tickers = [normalize_tw_ticker(str(item.get("Ticker", ""))) for item in active_port_list if item.get("Ticker")]
    active_capital = float(state.get("tw_capital", 300000.0))
    currency_label = "TWD"
else:
    active_universe = US_UNIVERSE
    active_custom = [t.strip().upper() for t in state.get("us_watchlist", "").split(",") if t.strip()]
    active_port_list = state.get("us_portfolio", [])
    active_port_tickers = [str(item.get("Ticker", "")).strip().upper() for item in active_port_list if item.get("Ticker")]
    active_capital = float(state.get("us_capital", 10000.0))
    currency_label = "USD"

@st.cache_data(ttl=180)
def run_sniper_screener_v6(universe_list, custom_list, port_list, auto_top_n, total_cap, risk_p, atr_m, mode_str, is_tw):
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
            if len(df) < 180:
                continue
            raw_histories[sym] = df
            
            close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
            curr_p = float(close.iloc[-1])
            prev_p = float(close.iloc[-2])
            pct_chg = ((curr_p - prev_p) / prev_p) * 100
            price_lookup[sym] = curr_p
            
            ma10 = float(close.rolling(10).mean().iloc[-1])
            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = float(close.rolling(50).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else ma50
            dist_ma20_pct = ((curr_p - ma20) / ma20) * 100
            dist_ma50_pct = ((curr_p - ma50) / ma50) * 100
            
            std20 = float(close.rolling(20).std().iloc[-1])
            bb_width_pct = ((4 * std20) / ma20) * 100 if ma20 > 0 else 20.0
            ret_10d_pct = ((curr_p - float(close.iloc[-11])) / float(close.iloc[-11])) * 100 if len(close) > 11 else 0.0
            
            avg_vol20 = float(vol.rolling(20).mean().iloc[-1])
            rvol = float(vol.iloc[-1]) / avg_vol20 if avg_vol20 > 0 else 1.0
            
            recent_10_chg = close.diff().tail(11).iloc[:-1]
            recent_10_vol = vol.tail(11).iloc[:-1]
            down_vols = recent_10_vol[recent_10_chg < 0]
            max_down_vol = float(down_vols.max()) if not down_vols.empty else 0.0
            is_pocket_pivot = (pct_chg > 0.5) and (float(vol.iloc[-1]) > max_down_vol) and (curr_p >= ma10) and (-1.5 <= dist_ma20_pct <= 5.5)
            
            mfm = ((close - low) - (high - close)) / (high - low + 1e-9)
            cmf20 = float((mfm * vol).rolling(20).sum().iloc[-1] / (vol.rolling(20).sum().iloc[-1] + 1e-9))
            
            obv = (vol * close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))).cumsum()
            obv_high_20 = float(obv.tail(20).max())
            price_high_20 = float(close.tail(20).max())
            is_obv_leading = (float(obv.iloc[-1]) >= obv_high_20 * 0.98) and (curr_p < price_high_20 * 0.97)
            
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
            is_macd_turning_up = (hist_curr > 0 and hist_prev <= 0) or (hist_curr > hist_prev and hist_curr > -0.8)
            
            tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
            stop_loss_price = curr_p - (atr_m * atr14)
            atr_stop_lookup[sym] = stop_loss_price
            risk_per_share = curr_p - stop_loss_price
            suggested_shares = int((total_cap * (risk_p / 100.0)) // risk_per_share) if risk_per_share > 0 else 0

            if is_sniper_mode:
                pos_pts = 0
                if curr_p > ma200: pos_pts += 10
                if -2.5 <= dist_ma20_pct <= 3.5:
                    pos_pts += 20
                elif -4.0 <= dist_ma50_pct <= 2.5 and curr_p > ma200:
                    pos_pts += 18
                elif 3.5 < dist_ma20_pct <= 6.5:
                    pos_pts += 10
                elif dist_ma20_pct > 8.5:
                    pos_pts -= 15
                    
                cmf_clamped = max(-0.20, min(0.25, cmf20))
                stealth_pts = int(((cmf_clamped + 0.20) / 0.45) * 22)
                if (abs(ret_10d_pct) <= 5.0 and cmf20 >= 0.08) or is_obv_leading:
                    stealth_pts += 8
                    
                squeeze_pts = 20 if bb_width_pct <= 10.0 else (15 if bb_width_pct <= 15.0 else (10 if bb_width_pct <= 22.0 else 4))
                    
                trigger_pts = 0
                if is_pocket_pivot: trigger_pts += 9
                if is_macd_turning_up: trigger_pts += 6
                if 42 <= rsi14 <= 64: trigger_pts += 5
                elif 35 <= rsi14 < 42: trigger_pts += 4
                
                total_score = int(min(99, max(10, pos_pts + stealth_pts + squeeze_pts + trigger_pts)))
                
                if is_pocket_pivot and cmf20 > 0.05:
                    setup_tag = "🟢 口袋支點剛點火 (起漲第1根)"
                elif bb_width_pct <= 14.0 and cmf20 >= 0.06 and abs(dist_ma20_pct) <= 4.0:
                    setup_tag = "🟢 VCP 波動壓縮蓄勢 (爆發前夕)"
                elif (abs(ret_10d_pct) <= 4.5 and cmf20 >= 0.10) or is_obv_leading:
                    setup_tag = "🟢 主力橫盤暗池吃貨 (籌碼背離)"
                elif (-3.0 <= dist_ma20_pct <= 2.0 or -3.0 <= dist_ma50_pct <= 2.5) and curr_p > ma200 and cmf20 > 0:
                    setup_tag = "🟢 回測均線黃金支撐 (低風險買點)"
                elif dist_ma20_pct > 8.0 or rsi14 > 72:
                    setup_tag = "🔴 短線已高 (乖離過大勿追高)"
                elif total_score <= 40:
                    setup_tag = "🔴 籌碼渙散 / 空頭整理"
                else:
                    setup_tag = "🟡 築底觀察中 (等待點火)"
            else:
                trend_pts = (12 if curr_p > ma20 else 0) + (10 if curr_p > ma50 else 0) + (10 if curr_p > ma200 else 0) + (8 if ma20 > ma50 > ma200 else 0)
                cmf_pts = int(((max(-0.25, min(0.25, cmf20)) + 0.25) / 0.50) * 30)
                rvol_pts = int(min(20, max(0, (rvol - 0.5) * 13))) if pct_chg >= 0 else int(max(0, 10 - (rvol - 0.8) * 10))
                rsi_pts = 10 if 50 <= rsi14 <= 72 else 5
                total_score = int(min(99, max(10, trend_pts + cmf_pts + rvol_pts + rsi_pts)))
                setup_tag = "🟢 強勢突破推進" if total_score >= 75 else "🟡 區間震盪"

            scored_items.append({
                "sym": sym, "display_name": format_symbol_display(sym, is_tw),
                "score": total_score, "setup_tag": setup_tag,
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
            if is_port: tags.append("持倉")
            if is_custom: tags.append("自選")
            if not tags or item["score"] >= 72: tags.append("系統優選")
            source_tag = " / ".join(tags)
            
            f_info = get_earnings_and_fundamentals(sym)
            setup_display = f"🔴 財報將至 ({f_info['days_to_earnings']}天)" if 0 <= f_info["days_to_earnings"] <= 7 else item["setup_tag"]
                
            final_rows.append({
                "標的代號": item["display_name"],
                "_raw_sym": sym,
                "入選來源": source_tag,
                "潛伏狙擊分": item["score"],
                "爆發前夕型態": setup_display,
                "離20MA乖離 (%)": round(item["dist_ma20"], 1),
                "布林壓縮寬度 (%)": round(item["bb_width"], 1),
                "CMF 主力吃貨": round(item["cmf20"], 3),
                "RVOL 量比": round(item["rvol"], 2),
                f"現價 ({currency_label})": round(item["curr_p"], 2),
                "單日漲跌 (%)": round(item["pct_chg"], 2),
                "近20日走勢": item["trend_20d"],
                f"ATR 停損價 ({currency_label})": round(item["stop_loss"], 2),
                "建議買進股數": item["shares"],
                "下次財報日": f_info["earnings_str"]
            })
            
    return pd.DataFrame(final_rows), raw_histories, price_lookup, atr_stop_lookup

with st.spinner(f"正在掃描 {mkt_title} 核心標的池：尋找「布林壓縮蓄勢、主力暗池吃貨、貼近均線剛起漲」之潛伏標的..."):
    df_scan, histories, live_prices, live_stops = run_sniper_screener_v6(
        active_universe, active_custom, active_port_tickers,
        state["auto_pick_count"], active_capital, state["risk_pct"], state["atr_mult"],
        state.get("strategy_mode", ""), is_tw_market
    )

# ==========================================
# 模組三：我的持倉部位與預算管理中心
# ==========================================
st.subheader(f"模組三：{mkt_title} 持倉倉位與預算損益管理 (記憶碼：{st.session_state.current_pin})")

col_port_edit, col_port_summary = st.columns([1.4, 2.6])

with col_port_edit:
    st.markdown("##### 編輯持倉清單 (台股輸入代號如 0050 或 2330)")
    port_df_input = pd.DataFrame(active_port_list) if active_port_list else pd.DataFrame(columns=["Ticker", "Shares", "Avg_Cost"])
    edited_port_df = st.data_editor(
        port_df_input, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "Ticker": st.column_config.TextColumn("股票代號", required=True),
            "Shares": st.column_config.NumberColumn("持有股數", min_value=0.0, step=1.0, required=True),
            "Avg_Cost": st.column_config.NumberColumn(f"買進成本 ({currency_label})", min_value=0.01, step=0.5, required=True)
        }
    )
    cleaned_port = []
    for _, r in edited_port_df.iterrows():
        t_val = str(r.get("Ticker", "")).strip().upper()
        if is_tw_market and t_val:
            t_val = normalize_tw_ticker(t_val)
        s_val = float(r.get("Shares", 0) or 0)
        c_val = float(r.get("Avg_Cost", 0) or 0)
        if t_val and s_val > 0:
            cleaned_port.append({"Ticker": t_val, "Shares": s_val, "Avg_Cost": c_val})
            
    port_key = "tw_portfolio" if is_tw_market else "us_portfolio"
    if cleaned_port != state.get(port_key):
        state[port_key] = cleaned_port
        sync_state()
        st.rerun()

with col_port_summary:
    st.markdown("##### 倉位即時損益與 ATR 停損診斷")
    port_eval_rows = []
    total_market_val, total_cost_val = 0.0, 0.0
    
    for item in state.get(port_key, []):
        sym = normalize_tw_ticker(item["Ticker"]) if is_tw_market else item["Ticker"]
        shares, cost = item["Shares"], item["Avg_Cost"]
        curr_p = live_prices.get(sym, cost)
        stop_p = live_stops.get(sym, curr_p * 0.92)
        
        mkt_val, cost_val = shares * curr_p, shares * cost
        pnl_val = mkt_val - cost_val
        pnl_pct = ((curr_p - cost) / cost) * 100 if cost > 0 else 0.0
        total_market_val += mkt_val
        total_cost_val += cost_val
        
        if curr_p <= stop_p:
            action_hint = "🔴 觸及 ATR 停損！建議執行風控"
        elif pnl_pct >= 15:
            action_hint = "🟢 獲利豐厚，可上移停損鎖利"
        else:
            action_hint = "🟢 正常續抱 (守穩停損線之上)"
            
        port_eval_rows.append({
            "標的": format_symbol_display(sym, is_tw_market),
            "股數": shares,
            "成本價": round(cost, 2),
            "現價": round(curr_p, 2),
            f"持倉市值 ({currency_label})": round(mkt_val, 0 if is_tw_market else 2),
            f"未實現損益 ({currency_label})": round(pnl_val, 0 if is_tw_market else 2),
            "報酬率 (%)": round(pnl_pct, 2),
            "ATR 停損價": round(stop_p, 2),
            "倉位診斷": action_hint
        })
        
    remaining_cash = active_capital - total_cost_val
    total_equity = remaining_cash + total_market_val
    total_pnl = total_market_val - total_cost_val
    pos_ratio = (total_market_val / total_equity * 100) if total_equity > 0 else 0.0
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"總資產淨值 ({currency_label})", f"{total_equity:,.0f}" if is_tw_market else f"${total_equity:,.2f}", f"{total_pnl:+,.0f}" if is_tw_market else f"{total_pnl:+,.2f}")
    m2.metric("目前持倉總市值", f"{total_market_val:,.0f}" if is_tw_market else f"${total_market_val:,.2f}", f"水位佔比 {pos_ratio:.1f}%", delta_color="off")
    m3.metric("剩餘可用現金", f"{remaining_cash:,.0f}" if is_tw_market else f"${remaining_cash:,.2f}")
    m4.metric("設定總預算基準", f"{active_capital:,.0f}" if is_tw_market else f"${active_capital:,.0f}")
    
    if port_eval_rows:
        st.dataframe(pd.DataFrame(port_eval_rows), use_container_width=True, hide_index=True)

st.divider()

# ==========================================
# 模組四：起漲前潛伏狙擊雷達總表
# ==========================================
st.subheader(f"模組四：{mkt_title} 起漲前夕潛伏狙擊雷達總表")

col_f1, col_f2, col_f3 = st.columns([1.2, 1.5, 2.3])
with col_f1:
    if st.button("立即重新掃描潛伏買點", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
with col_f2:
    hide_overextended = st.checkbox("自動隱藏「已漲高(乖離>8%)」標的", value=True)
with col_f3:
    only_stealth_inflow = st.checkbox("只顯示「主力暗池吃貨中 (CMF > 0)」", value=False)

if not df_scan.empty:
    df_show = df_scan.copy()
    if hide_overextended:
        df_show = df_show[(df_show["離20MA乖離 (%)"] <= 8.0) | (df_show["入選來源"].str.contains("持倉|自選"))]
    if only_stealth_inflow:
        df_show = df_show[df_show["CMF 主力吃貨"] > 0]
        
    st.dataframe(
        df_show.drop(columns=["_raw_sym"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "潛伏狙擊分": st.column_config.ProgressColumn("潛伏爆發分 (0-100)", format="%d 分", min_value=0, max_value=100),
            "離20MA乖離 (%)": st.column_config.NumberColumn("離月線距離 (%)", format="%+.1f%%"),
            "布林壓縮寬度 (%)": st.column_config.NumberColumn("布林壓縮率 (%)", format="%.1f%%"),
            "近20日走勢": st.column_config.LineChartColumn("近20日走勢"),
            "單日漲跌 (%)": st.column_config.NumberColumn("今日漲跌", format="%+.2f%%")
        }
    )

st.divider()

# ==========================================
# 模組五：布林壓縮通道 ＋ OBV 領先指標 ＋ 觸控 K 線看盤室
# ==========================================
st.subheader("模組五：爆發前夕 K 線解剖室 (支援雙指捏合縮放 ＆ 單指滑動平移)")

if not df_scan.empty:
    raw_sym_list = df_scan["_raw_sym"].tolist()
    display_map = dict(zip(df_scan["_raw_sym"], df_scan["標的代號"]))
    
    last_key = "tw_last_ticker" if is_tw_market else "us_last_ticker"
    saved_last = state.get(last_key, raw_sym_list[0])
    default_idx = raw_sym_list.index(saved_last) if saved_last in raw_sym_list else 0
    
    c_sel1, c_sel2 = st.columns([1.2, 1.8])
    with c_sel1:
        selected_ticker = st.selectbox(
            "選擇要解剖的標的：",
            raw_sym_list,
            index=default_idx,
            format_func=lambda x: display_map.get(x, x)
        )
        if selected_ticker != state.get(last_key):
            state[last_key] = selected_ticker
            sync_state()
    with c_sel2:
        timeframe = st.radio(
            "選擇 K 線週期：",
            ["波段潛伏日 K 線 (含布林壓縮軌 + 均線 + CMF & OBV 籌碼)", "盤中 5 分鐘 K 線 (含當日重置 VWAP 均價線)", "盤中 15 分鐘 K 線 (短波段拐點)"],
            horizontal=True
        )
        
    touch_chart_config = {
        'scrollZoom': True,
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['select2d', 'lasso2d']
    }
    
    sel_title = display_map.get(selected_ticker, selected_ticker)
        
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
                f"{sel_title} 日 K 線 ＋ 布林壓縮通道 (紫虛線) ＋ 20MA / 50MA",
                "CMF 主力暗池資金流 (綠柱＝主力吃貨 / 紅柱＝主力出貨)",
                "OBV 能量潮累積線 (黃線若比股價提早創高＝爆發前主力鎖碼)"
            )
        )
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Upper'], line=dict(color='rgba(171, 71, 188, 0.6)', width=1, dash='dot'), name='布林上軌'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Lower'], line=dict(color='rgba(171, 71, 188, 0.6)', width=1, dash='dot'), fill='tonexty', fillcolor='rgba(171, 71, 188, 0.07)', name='布林壓縮區'), row=1, col=1)
        fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'], name="日K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA20'], line=dict(color='#FFA726', width=1.8), name='20MA (月線)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA50'], line=dict(color='#29B6F6', width=1.8), name='50MA (季線)'), row=1, col=1)
        
        cmf_colors = ['#26a69a' if v >= 0 else '#ef5350' for v in df_plot['CMF']]
        fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['CMF'], marker_color=cmf_colors, name="CMF 籌碼"), row=2, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)
        
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['OBV'], line=dict(color='#FFEE58', width=2), name="OBV 能量潮"), row=3, col=1)
        
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        fig.update_layout(height=750, xaxis_rangeslider_visible=False, template="plotly_dark", dragmode="pan")
        fig.update_yaxes(fixedrange=False)
        st.plotly_chart(fig, use_container_width=True, config=touch_chart_config)
    else:
        interval_str = "5m" if "5 分鐘" in timeframe else "15m"
        period_str = "5d" if interval_str == "5m" else "1mo"
        with st.spinner(f"正在載入 {sel_title} 的 {interval_str} 盤中即時 K 線..."):
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
                subplot_titles=(f"{sel_title} 盤中 {interval_str} K 線 (20EMA 與 每日重置機構 VWAP)", "盤中分時成交量")
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
# 模組六：個股財報基本面 ＆ 個股專屬繁中新聞
# ==========================================
st.subheader(f"模組六：{sel_title} 財報基本面體質與個股最新消息")

col_fund, col_news = st.columns([1.2, 1.8])

with col_fund:
    st.markdown(f"#### {sel_title} 財報與機構目標價診斷")
    f_data = get_earnings_and_fundamentals(selected_ticker)
    curr_price_sel = float(histories[selected_ticker]['Close'].iloc[-1])
    
    f1, f2 = st.columns(2)
    f1.metric("下次財報公布日", f_data["earnings_str"])
    if f_data["target_price"]:
        upside = ((f_data["target_price"] - curr_price_sel) / curr_price_sel) * 100
        f2.metric("機構平均目標價", f"{f_data['target_price']:.2f}", f"{upside:+.1f}% 潛在空間")
    else:
        f2.metric("機構平均目標價", "暫無數據")
        
    f3, f4 = st.columns(2)
    f3.metric("本益比 (P/E)", f"{f_data['pe_forward']:.1f} 倍" if f_data["pe_forward"] else "暫無數據")
    f4.metric("分析師共識評級", f_data["recommendation_zh"])
    
    f5, f6 = st.columns(2)
    f5.metric("營收年增率 (YoY)", f"{f_data['rev_growth']*100:+.1f}%" if f_data["rev_growth"] else "暫無數據")
    f6.metric("企業淨利率", f"{f_data['profit_margin']*100:.1f}%" if f_data["profit_margin"] else "暫無數據")

with col_news:
    st.markdown(f"#### {sel_title} 最新繁體中文財經新聞")
    clean_query_name = TW_NAME_MAP.get(selected_ticker, selected_ticker.replace(".TW", "")) if is_tw_market else f"{selected_ticker} 美股"
    stock_zh_news = fetch_native_zh_news(clean_query_name)
    if stock_zh_news:
        for n in stock_zh_news:
            st.markdown(
                f"**{n['sentiment']} ｜ [{n['title']}]({n['link']})**  \n"
                f"<span style='color:gray;font-size:12px;'>媒體來源：{n['source']} ｜ 時間：{n['time']}</span>",
                unsafe_allow_html=True
            )
    else:
        st.write("暫無最新個股新聞。")

if auto_refresh:
    time.sleep(refresh_sec)
    st.cache_data.clear()
    st.rerun()
