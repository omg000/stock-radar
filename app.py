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
st.set_page_config(page_title="美股量化實戰雷達 4.1", page_icon="🦅", layout="wide")

# ==========================================
# 6位數簡易通行碼 (PIN) 記憶保險箱引擎
# ==========================================
VAULT_FILE = "pin_vault_v4.json"

DEFAULT_STATE = {
    "capital": 10000.0,
    "risk_pct": 1.5,
    "atr_mult": 2.0,
    "custom_watchlist": "NVDA, TSLA, PLTR",
    "last_selected_ticker": "NVDA",
    "auto_pick_count": 12,
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

# 讀取網址上的 ?pin= 參數，預設為 888999
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
# 內建市場母體池 (供系統自動海選最強勢標的)
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
        detail = "目前為休市時段，系統顯示為最新一個交易日之收盤與籌碼數據。"
    elif open_t <= curr_time < close_t:
        close_dt = datetime.combine(now_et.date(), close_t, tzinfo=ZoneInfo("America/New_York"))
        rem = close_dt - now_et
        hrs, rem_s = divmod(int(rem.total_seconds()), 3600)
        mins = rem_s // 60
        status_badge = f"🟢 美股正規盤交易中 (Market OPEN) ｜ 距離收盤剩餘 {hrs}小時 {mins}分"
        detail = "盤中即時報價與分時 K 線跳動中！"
    elif pre_t <= curr_time < open_t:
        open_dt = datetime.combine(now_et.date(), open_t, tzinfo=ZoneInfo("America/New_York"))
        rem = open_dt - now_et
        hrs, rem_s = divmod(int(rem.total_seconds()), 3600)
        mins = rem_s // 60
        status_badge = f"🌅 美股盤前交易時段 (Pre-Market) ｜ 距離正式開盤剩餘 {hrs}小時 {mins}分"
        detail = "即將開盤，可留意盤前跳空與財報新聞。"
    elif close_t <= curr_time < after_t:
        status_badge = "🌙 美股盤後交易時段 (After-Hours)"
        detail = "正規盤已收盤，目前為盤後電子盤交易時段。"
    else:
        status_badge = "🔴 美股夜盤休市中"
        detail = "等待美東時間 04:00 盤前開市。"
        
    time_str = f"美東時間: {now_et.strftime('%Y-%m-%d %H:%M')} ET ｜ 🇹🇼 台灣時間: {now_tw.strftime('%Y-%m-%d %H:%M')}"
    return status_badge, detail, time_str

st.title("美股量化實戰追蹤系統 4.1")
mkt_badge, mkt_detail, mkt_clock = get_us_market_status()
st.info(f"**{mkt_badge}** \n {mkt_clock} ｜ {mkt_detail}")

# ==========================================
# 側邊欄：6位數記憶通行碼、自動選股與風控設定
# ==========================================
st.sidebar.header("🔑 6位數專屬記憶通行碼")
st.sidebar.caption("輸入約 6 碼英數組合（如 `888999` 或 `A12345`），系統會自動記憶並綁定你的預算、倉位與自選股！")

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
                st.sidebar.success(f"已載入 [{pin_input}] 的記憶！")
            else:
                save_to_vault(pin_input, st.session_state.user_state)
                st.sidebar.success(f"已建立新通行碼 [{pin_input}]！")
            st.rerun()

st.sidebar.markdown(f"目前綁定記憶碼：**`{st.session_state.current_pin}`** (已自動存檔)")
st.sidebar.divider()

auto_refresh = st.sidebar.toggle("開啟盤中自動更新", value=False)
refresh_sec = st.sidebar.selectbox("自動更新頻率 (秒)", [60, 180, 300], index=1)

st.sidebar.subheader("系統自動選股 + 自選清單")
new_auto_count = st.sidebar.slider("系統自動海選強勢股數量", min_value=5, max_value=25, value=int(state["auto_pick_count"]), step=1)
new_watchlist = st.sidebar.text_area("⭐ 我的自選觀察清單 (逗號分隔)", value=state["custom_watchlist"], height=70)

st.sidebar.subheader("預算與量化風控 (自動記憶)")
new_capital = st.sidebar.number_input("我的總投資預算 (USD)", min_value=500.0, value=float(state["capital"]), step=500.0)
new_risk = st.sidebar.slider("單筆最大承受虧損 (%)", 0.5, 5.0, float(state["risk_pct"]), 0.5)
new_atr = st.sidebar.slider("ATR 停損寬度 (倍)", 1.0, 4.0, float(state["atr_mult"]), 0.5)

if (new_auto_count != state["auto_pick_count"] or new_watchlist != state["custom_watchlist"] or
    new_capital != state["capital"] or new_risk != state["risk_pct"] or new_atr != state["atr_mult"]):
    state["auto_pick_count"] = new_auto_count
    state["custom_watchlist"] = new_watchlist
    state["capital"] = new_capital
    state["risk_pct"] = new_risk
    state["atr_mult"] = new_atr
    sync_state()

st.sidebar.subheader("表格快速過濾")
min_score = st.sidebar.slider("最低強度評分門檻", 0, 100, 0, 5)
only_inflow = st.sidebar.checkbox("只顯示「主力資金淨流入 (CMF > 0)」", value=False)

user_custom_list = [t.strip().upper() for t in state["custom_watchlist"].split(",") if t.strip()]
portfolio_tickers = [str(item.get("Ticker", "")).strip().upper() for item in state["portfolio"] if item.get("Ticker")]

# ==========================================
# 輔助函數：全中文財報基本面 ＆ 華爾街外電自動中文化
# ==========================================
RATING_MAP_ZH = {
    "STRONG_BUY": "強力買進",
    "BUY": "買進",
    "HOLD": "觀望持有",
    "UNDERPERFORM": "表現落後",
    "SELL": "賣出",
    "NONE": "暫無評級",
    "N/A": "暫無評級"
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
                    res["earnings_str"] = f"{e_date.strftime('%m/%d')} ({days_diff}天後)"
                elif days_diff > 14:
                    res["earnings_str"] = f"{e_date.strftime('%m/%d')} ({days_diff}天後)"
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
    """將華爾街英文新聞標題自動翻譯為繁體中文"""
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
        if is_macro:
            query = "US+stock+market+Wall+Street+Fed+S%26P500"
        else:
            query = f"{sym}+stock+wall+street+earnings"
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            root = ET.fromstring(response.read())
            for item in root.findall('.//item')[:7]:
                title_en = item.find('title').text if item.find('title') is not None else ""
                # 移除標題尾端重複的媒體名稱以利精準翻譯
                clean_en = title_en.rsplit(" - ", 1)[0] if " - " in title_en else title_en
                title_zh = translate_to_zh(clean_en)
                
                link = item.find('link').text if item.find('link') is not None else ""
                pub = item.find('source').text if item.find('source') is not None else "華爾街外電"
                pub_date = item.find('pubDate').text[:16] if item.find('pubDate') is not None else ""
                if title_en:
                    news_items.append({
                        "title_zh": title_zh,
                        "title_en": clean_en,
                        "link": link,
                        "publisher": pub,
                        "time": pub_date
                    })
    except Exception:
        pass
    return news_items

# ==========================================
# 模組一：全方位宏觀與市場情緒中心
# ==========================================
st.subheader("市場情緒")

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
        vix_status = "🟢 極度樂觀 (留意追高)" if vix < 15 else ("🟢 穩定偏多 (順勢做多)" if vix < 20 else ("🟠 警戒震盪 (縮小倉位)" if vix < 30 else "🔴 極度恐慌 (留意反轉)"))
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
            st.markdown("#####盤勢綜合診斷")
            if vix < 20 and spy['curr'] > spy['ma20'] and qqq['curr'] > qqq['ma20']:
                st.success("**🟢 多頭順風車**：大盤站穩月線且恐慌低，系統自動選股勝率高。")
            elif vix >= 25 or spy['curr'] < spy['ma50']:
                st.error("**🔴 風險警戒區**：大盤跌破季線或恐慌飆升，建議提高現金比例。")
            else:
                st.warning("**🟡 結構性震盪**：個股表現分化，優先鎖定高 CMF 吸籌標的。")
except Exception as e:
    st.warning(f"正在同步大盤宏觀數據... ({e})")

st.divider()

# ==========================================
# 全自動海選引擎 (掃描全市場母體池 + 自選股 + 持倉股)
# ==========================================
@st.cache_data(ttl=180)
def run_quant_screener(universe_list, custom_list, port_list, auto_top_n, total_cap, risk_p, atr_m):
    all_symbols = list(dict.fromkeys(universe_list + custom_list + port_list))
    data = yf.download(all_symbols, period="1y", interval="1d", group_by="ticker", progress=False)
    
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
            
            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = float(close.rolling(50).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1])
            
            avg_vol20 = float(vol.rolling(20).mean().iloc[-1])
            rvol = float(vol.iloc[-1]) / avg_vol20 if avg_vol20 > 0 else 1.0
            
            mfm = ((close - low) - (high - close)) / (high - low + 1e-9)
            cmf20 = float((mfm * vol).rolling(20).sum().iloc[-1] / (vol.rolling(20).sum().iloc[-1] + 1e-9))
            
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi14 = float(100 - (100 / (1 + (gain / (loss + 1e-9)).iloc[-1])))
            
            tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
            stop_loss_price = curr_p - (atr_m * atr14)
            atr_stop_lookup[sym] = stop_loss_price
            risk_per_share = curr_p - stop_loss_price
            suggested_shares = int((total_cap * (risk_p / 100.0)) // risk_per_share) if risk_per_share > 0 else 0

            trend_pts = (12 if curr_p > ma20 else 0) + (10 if curr_p > ma50 else 0) + (10 if curr_p > ma200 else 0) + (8 if ma20 > ma50 > ma200 else 0)
            cmf_pts = int(((max(-0.25, min(0.25, cmf20)) + 0.25) / 0.50) * 30)
            rvol_pts = int(min(20, max(0, (rvol - 0.5) * 13))) if pct_chg >= 0 else int(max(0, 10 - (rvol - 0.8) * 10))
            rsi_pts = 10 if 50 <= rsi14 <= 72 else (6 if (40 <= rsi14 < 50 or 72 < rsi14 <= 80) else 2)
            total_score = int(min(100, max(5, trend_pts + cmf_pts + rvol_pts + rsi_pts)))
            
            scored_items.append({
                "sym": sym, "score": total_score, "curr_p": curr_p, "pct_chg": pct_chg,
                "trend_20d": close.tail(20).tolist(), "cmf20": cmf20, "rvol": rvol,
                "rsi14": rsi14, "ma20": ma20, "stop_loss": stop_loss_price, "shares": suggested_shares
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
            if is_custom: tags.append("⭐自選")
            if not tags or item["score"] >= 75: tags.append("系統優選")
            source_tag = " / ".join(tags)
            
            f_info = get_earnings_and_fundamentals(sym)
            if 0 <= f_info["days_to_earnings"] <= 7:
                signal = "財報將至 (避開跳空)"
            elif item["score"] >= 80 and item["rvol"] >= 1.3:
                signal = "主力點火突破 (極強)"
            elif item["score"] >= 70:
                signal = "多頭穩健推進 (偏多)"
            elif item["cmf20"] >= 0.10 and item["curr_p"] < item["ma20"]:
                signal = "回檔暗池吸籌 (留意)"
            elif item["score"] <= 35:
                signal = "空頭走弱 / 主力撤退"
            else:
                signal = "區間整理 (等待方向)"
                
            final_rows.append({
                "代號": sym,
                "入選來源": source_tag,
                "強度評分": item["score"],
                "實戰訊號": signal,
                "下次財報日": f_info["earnings_str"],
                "現價 ($)": round(item["curr_p"], 2),
                "單日漲跌 (%)": round(item["pct_chg"], 2),
                "近20日走勢": item["trend_20d"],
                "CMF 主力資金": round(item["cmf20"], 3),
                "RVOL 量比": round(item["rvol"], 2),
                "ATR 停損價 ($)": round(item["stop_loss"], 2),
                "風控建議股數": item["shares"]
            })
            
    return pd.DataFrame(final_rows), raw_histories, price_lookup, atr_stop_lookup

with st.spinner("正在掃描全市場核心標的，自動海選最強趨勢股與計算持倉損益..."):
    df_scan, histories, live_prices, live_stops = run_quant_screener(
        MARKET_UNIVERSE, user_custom_list, portfolio_tickers,
        state["auto_pick_count"], state["capital"], state["risk_pct"], state["atr_mult"]
    )

# ==========================================
# 模組二：我的持倉部位與預算管理中心 (綁定 6位數通行碼)
# ==========================================
st.subheader(f"持倉倉位與預算損益管理（已綁定記憶碼：`{st.session_state.current_pin}`）")
st.caption("直接在左表修改股數與成本價、點底部 `+` 新增持倉，系統會自動存入你的 6 位數通行碼中！")

col_port_edit, col_port_summary = st.columns([1.4, 2.6])

with col_port_edit:
    st.markdown("#####編輯我的持倉清單")
    port_df_input = pd.DataFrame(state["portfolio"]) if state["portfolio"] else pd.DataFrame(columns=["Ticker", "Shares", "Avg_Cost"])
    edited_port_df = st.data_editor(
        port_df_input,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
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
    st.markdown("#####倉位即時損益與 ATR 停損診斷")
    port_eval_rows = []
    total_market_val = 0.0
    total_cost_val = 0.0
    
    for item in state["portfolio"]:
        sym = item["Ticker"]
        shares = item["Shares"]
        cost = item["Avg_Cost"]
        curr_p = live_prices.get(sym)
        if curr_p is None:
            try:
                curr_p = float(yf.Ticker(sym).fast_info['lastPrice'])
            except Exception:
                curr_p = cost
        stop_p = live_stops.get(sym, curr_p * 0.92)
        
        mkt_val = shares * curr_p
        cost_val = shares * cost
        pnl_usd = mkt_val - cost_val
        pnl_pct = ((curr_p - cost) / cost) * 100 if cost > 0 else 0.0
        
        total_market_val += mkt_val
        total_cost_val += cost_val
        
        if curr_p <= stop_p:
            action_hint = "觸及 ATR 停損！建議嚴格執行風控"
        elif pnl_pct >= 15:
            action_hint = "獲利豐厚，可將停損上移鎖住獲利"
        else:
            action_hint = "正常續抱 (守穩停損線之上)"
            
        port_eval_rows.append({
            "代號": sym,
            "股數": shares,
            "成本價": round(cost, 2),
            "現價": round(curr_p, 2),
            "持倉市值 ($)": round(mkt_val, 2),
            "未實現損益 ($)": round(pnl_usd, 2),
            "報酬率 (%)": round(pnl_pct, 2),
            "ATR 防守停損價": round(stop_p, 2),
            "倉位診斷": action_hint
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
        st.dataframe(
            pd.DataFrame(port_eval_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "未實現損益 ($)": st.column_config.NumberColumn("損益 ($)", format="$%+.2f"),
                "報酬率 (%)": st.column_config.NumberColumn("報酬率 (%)", format="%+.2f%%")
            }
        )
    else:
        st.info("目前尚無持倉部位，可在左側表格新增你買進的股票與成本價！")

st.divider()

# ==========================================
# 模組三：系統自動海選強勢股 ＋ 自選股雷達總表
# ==========================================
st.subheader("AI 演算法全市場自動海選強勢股 ＆ 自選股雷達")
st.caption(f"系統已從美股 45+ 檔核心標的池中，自動海選出 **Top {state['auto_pick_count']} 最強勢標的（系統優選）**，並合併你的 **⭐自選觀察** 與 **持倉部位**！")

col_b1, col_b2 = st.columns([1, 4])
with col_b1:
    if st.button("立即重新掃描全市場", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

if not df_scan.empty:
    df_filtered = df_scan[df_scan["強度評分"] >= min_score]
    if only_inflow:
        df_filtered = df_filtered[df_filtered["CMF 主力資金"] > 0]
        
    st.dataframe(
        df_filtered,
        use_container_width=True,
        hide_index=True,
        column_config={
            "強度評分": st.column_config.ProgressColumn("綜合強度 (0-100)", format="%d 分", min_value=0, max_value=100),
            "下次財報日": st.column_config.TextColumn("財報避雷針"),
            "近20日走勢": st.column_config.LineChartColumn("近20日趨勢線"),
            "單日漲跌 (%)": st.column_config.NumberColumn("漲跌幅 (%)", format="%+.2f%%"),
            "CMF 主力資金": st.column_config.NumberColumn("CMF 籌碼流", help=">0 代表主力買超吸籌，>0.1 為強烈買進"),
            "RVOL 量比": st.column_config.NumberColumn("RVOL 爆量倍數", help=">1.3 代表明顯放量")
        }
    )

st.divider()

# ==========================================
# 模組四：記憶上次瀏覽標的之直覺觸控 K 線看盤室
# ==========================================
st.subheader(" K 線")
st.caption("操作小撇步：在 K 線圖上直接用「單指左右滑動」可平移時間軸，用「雙指張開/捏合（或滑鼠滾輪）」可自由放大縮小！")

if not df_scan.empty:
    available_tickers = df_scan["代號"].tolist()
    default_idx = available_tickers.index(state["last_selected_ticker"]) if state["last_selected_ticker"] in available_tickers else 0
    
    c_sel1, c_sel2 = st.columns([1, 2])
    with c_sel1:
        selected_ticker = st.selectbox("選擇深度剖析標的 (自動記憶)：", available_tickers, index=default_idx)
        if selected_ticker != state["last_selected_ticker"]:
            state["last_selected_ticker"] = selected_ticker
            sync_state()
    with c_sel2:
        timeframe = st.radio(
            "選擇 K 線週期：",
            ["波段日 K 線 (含 20/50/200 均線 + CMF 籌碼)", "盤中 5 分鐘 K 線 (含當日重置 VWAP 機構均價)", "盤中 15 分鐘 K 線 (近1個月短波段)"],
            horizontal=True
        )
        
    touch_chart_config = {
        'scrollZoom': True,
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['select2d', 'lasso2d']
    }
        
    if "波段日 K" in timeframe:
        df_plot = histories[selected_ticker].tail(150).copy()
        df_plot['MA20'] = df_plot['Close'].rolling(20).mean()
        df_plot['MA50'] = df_plot['Close'].rolling(50).mean()
        df_plot['MA200'] = df_plot['Close'].rolling(200).mean()
        mfm = ((df_plot['Close'] - df_plot['Low']) - (df_plot['High'] - df_plot['Close'])) / (df_plot['High'] - df_plot['Low'] + 1e-9)
        df_plot['CMF'] = (mfm * df_plot['Volume']).rolling(20).sum() / (df_plot['Volume'].rolling(20).sum() + 1e-9)
        
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.58, 0.18, 0.24],
            subplot_titles=(f"{selected_ticker} 日 K 線 (20MA / 50MA / 200MA)", "成交量 (Volume)", "CMF 主力資金流向 (綠柱吸籌 / 紅柱出貨)")
        )
        fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'], name="日K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA20'], line=dict(color='#FFA726', width=1.5), name='20MA'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA50'], line=dict(color='#29B6F6', width=1.5), name='50MA'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA200'], line=dict(color='#AB47BC', width=1.5, dash='dot'), name='200MA'), row=1, col=1)
        
        vol_colors = ['#ef5350' if c < o else '#26a69a' for c, o in zip(df_plot['Close'], df_plot['Open'])]
        fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=vol_colors, name="成交量"), row=2, col=1)
        
        cmf_colors = ['#26a69a' if v >= 0 else '#ef5350' for v in df_plot['CMF']]
        fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['CMF'], marker_color=cmf_colors, name="CMF 資金流"), row=3, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="gray", row=3, col=1)
        
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        fig.update_layout(height=720, xaxis_rangeslider_visible=False, template="plotly_dark", dragmode="pan")
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
st.subheader(f"：{selected_ticker} 財報基本面 ＆ 華爾街即時新聞")

col_fund, col_news = st.columns([1.2, 1.8])

with col_fund:
    st.markdown(f"#### {selected_ticker} 財報與機構目標價診斷")
    f_data = get_earnings_and_fundamentals(selected_ticker)
    curr_price_sel = float(histories[selected_ticker]['Close'].iloc[-1])
    
    f1, f2 = st.columns(2)
    f1.metric("下次財報公布日", f_data["earnings_str"])
    if f_data["target_price"]:
        upside = ((f_data["target_price"] - curr_price_sel) / curr_price_sel) * 100
        f2.metric("華爾街平均目標價", f"${f_data['target_price']:.2f}", f"{upside:+.1f}% 潛在空間")
    else:
        f2.metric("華爾街平均目標價", "暫無數據")
        
    f3, f4 = st.columns(2)
    f3.metric("預估本益比 (Forward P/E)", f"{f_data['pe_forward']:.1f} 倍" if f_data["pe_forward"] else "暫無數據")
    f4.metric("機構分析師共識評級", f_data["recommendation_zh"])
    
    f5, f6 = st.columns(2)
    f5.metric("營收年增率 (YoY)", f"{f_data['rev_growth']*100:+.1f}%" if f_data["rev_growth"] else "暫無數據")
    f6.metric("企業淨利率", f"{f_data['profit_margin']*100:.1f}%" if f_data["profit_margin"] else "暫無數據")

    st.info("**財報實戰守則**：若距離財報公布不到 **7 天**，建議先避開或減碼，防止財報開獎瞬間發生跳空風險。")

with col_news:
    news_tab1, news_tab2 = st.tabs([f"{selected_ticker} 最新外電", "華爾街大盤總經頭條"])
    
    with news_tab1:
        ticker_news = fetch_zh_wallstreet_news(selected_ticker, is_macro=False)
        if ticker_news:
            for n in ticker_news:
                st.markdown(
                    f"**• [{n['title_zh']}]({n['link']})**  \n"
                    f"<span style='color:#9e9e9e;font-size:12px;'>🇺🇸 原題：{n['title_en']}</span>  \n"
                    f"<span style='color:gray;font-size:12px;'>來源：{n['publisher']} ｜{n['time']}</span>",
                    unsafe_allow_html=True
                )
        else:
            st.write("暫無最新個股外電新聞。")
            
    with news_tab2:
        macro_news = fetch_zh_wallstreet_news("SPY", is_macro=True)
        if macro_news:
            for n in macro_news:
                st.markdown(
                    f"**• [{n['title_zh']}]({n['link']})**  \n"
                    f"<span style='color:#9e9e9e;font-size:12px;'>🇺🇸 原題：{n['title_en']}</span>  \n"
                    f"<span style='color:gray;font-size:12px;'>來源：{n['publisher']} ｜{n['time']}</span>",
                    unsafe_allow_html=True
                )
        else:
            st.write("暫無最新大盤總經頭條。")

if auto_refresh:
    time.sleep(refresh_sec)
    st.cache_data.clear()
    st.rerun()
