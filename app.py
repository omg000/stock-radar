import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 網頁基本設定
st.set_page_config(page_title="美股量化實戰雷達 Pro", page_icon="🦅", layout="wide")

st.title("🦅 美股量化實戰追蹤系統 Pro")
st.caption("整合：大盤情緒溫度計 ｜ 主力資金流 (CMF) ｜ 相對爆量 (RVOL) ｜ 均線趨勢 ｜ ATR 動態風控")

# ==========================================
# 側邊欄：參數與自選股設定 (手機端點左上角箭頭展開)
# ==========================================
st.sidebar.header("⚙️ 系統與風控參數")

default_tickers = "NVDA, AAPL, MSFT, AMZN, META, TSLA, PLTR, AMD, AVGO, CRWD, LLY, SMCI, COIN"
user_tickers = st.sidebar.text_area("📋 監控標的清單 (逗號分隔)", default_tickers, height=100)
tickers = [t.strip().upper() for t in user_tickers.split(",") if t.strip()]

st.sidebar.subheader("🛡️ 量化風控計算器")
capital = st.sidebar.number_input("總投資本金 (USD)", min_value=500, value=10000, step=500)
risk_pct = st.sidebar.slider("單筆最大承受虧損 (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.5)
atr_mult = st.sidebar.slider("ATR 停損寬度 (倍)", min_value=1.0, max_value=4.0, value=2.0, step=0.5)

st.sidebar.subheader("🔍 條件過濾器")
only_uptrend = st.sidebar.checkbox("只顯示「多頭排列」標的", value=False)
only_inflow = st.sidebar.checkbox("只顯示「主力資金淨流入 (CMF>0)」", value=False)

# ==========================================
# 模組一：大盤情緒與宏觀溫度計
# ==========================================
st.subheader("🧭 模組一：大盤情緒與環境定調")

@st.cache_data(ttl=300) # 快取 5 分鐘，確保盤中刷新夠快又不被鎖 IP
def get_macro_sentiment():
    macro_symbols = ["^VIX", "SPY", "QQQ"]
    data = yf.download(macro_symbols, period="6mo", interval="1d", progress=False)
    if isinstance(data.columns, pd.MultiIndex):
        close = data['Close']
    else:
        close = data
        
    vix_curr = float(close['^VIX'].dropna().iloc[-1])
    vix_prev = float(close['^VIX'].dropna().iloc[-2])
    vix_diff = vix_curr - vix_prev
    
    spy_s = close['SPY'].dropna()
    spy_curr = float(spy_s.iloc[-1])
    spy_ma20 = float(spy_s.rolling(20).mean().iloc[-1])
    spy_ma50 = float(spy_s.rolling(50).mean().iloc[-1])
    spy_chg = float(((spy_curr - spy_s.iloc[-2]) / spy_s.iloc[-2]) * 100)
    
    qqq_s = close['QQQ'].dropna()
    qqq_curr = float(qqq_s.iloc[-1])
    qqq_chg = float(((qqq_curr - qqq_s.iloc[-2]) / qqq_s.iloc[-2]) * 100)
    
    return vix_curr, vix_diff, spy_curr, spy_chg, spy_ma20, spy_ma50, qqq_curr, qqq_chg

try:
    vix_val, vix_diff, spy_val, spy_chg, spy_ma20, spy_ma50, qqq_val, qqq_chg = get_macro_sentiment()
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("VIX 恐慌指數", f"{vix_val:.2f}", f"{vix_diff:+.2f}", delta_color="inverse")
    with col2:
        st.metric("標普 500 (SPY)", f"${spy_val:.2f}", f"{spy_chg:+.2f}%")
    with col3:
        st.metric("納斯達克 (QQQ)", f"${qqq_val:.2f}", f"{qqq_chg:+.2f}%")
    with col4:
        if vix_val < 18 and spy_val > spy_ma20:
            st.success("🟢 **大盤環境：積極進攻**\n\n指數站穩月線且恐慌低迷，適合順勢操作強勢突破股。")
        elif vix_val > 25 or spy_val < spy_ma50:
            st.error("🔴 **大盤環境：防禦警戒**\n\n市場波動劇烈或跌破季線，建議縮小倉位、嚴格停損。")
        else:
            st.warning("🟡 **大盤環境：震盪選股**\n\n大盤處於整理期，建議買黑不買紅，鎖定主力高吸籌個股。")
except Exception as e:
    st.warning(f"大盤數據載入中或暫時無法取得: {e}")

st.divider()

# ==========================================
# 模組二：主力動向、趨勢與風控掃描表
# ==========================================
st.subheader("📡 模組二：主力動向與趨勢雷達掃描")

@st.cache_data(ttl=180) # 快取 3 分鐘，適合盤中更新
def scan_stocks(ticker_list, total_cap, risk_p, atr_m):
    results = []
    raw_histories = {}
    
    for sym in ticker_list:
        try:
            df = yf.download(sym, period="1y", interval="1d", progress=False)
            if len(df) < 200:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            df = df.dropna()
            raw_histories[sym] = df
            
            close = df['Close']
            high = df['High']
            low = df['Low']
            vol = df['Volume']
            
            curr_p = float(close.iloc[-1])
            prev_p = float(close.iloc[-2])
            pct_chg = ((curr_p - prev_p) / prev_p) * 100
            
            # 1. 均線系統
            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = float(close.rolling(50).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1])
            
            # 2. 相對成交量 (RVOL) & 日均成交額 (過濾流動性)
            avg_vol20 = float(vol.rolling(20).mean().iloc[-1])
            rvol = float(vol.iloc[-1]) / avg_vol20 if avg_vol20 > 0 else 0
            dollar_vol_m = (curr_p * avg_vol20) / 1e6 # 百萬美元
            
            # 3. 蔡金資金流向 (CMF 20日) - 判斷主力吸籌或出貨
            mfm = ((close - low) - (high - close)) / (high - low + 1e-9)
            mfv = mfm * vol
            cmf20 = float(mfv.rolling(20).sum().iloc[-1] / (vol.rolling(20).sum().iloc[-1] + 1e-9))
            
            # 4. RSI (14日) - 判斷是否過熱或超賣
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss + 1e-9)
            rsi14 = float(100 - (100 / (1 + rs.iloc[-1])))
            
            # 5. ATR (14日真實波幅) 與 動態停損/倉位計算
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
            
            stop_loss_price = curr_p - (atr_m * atr14)
            risk_per_share = curr_p - stop_loss_price
            max_loss_usd = total_cap * (risk_p / 100.0)
            suggested_shares = int(max_loss_usd // risk_per_share) if risk_per_share > 0 else 0
            
            # 6. 綜合演算法評分與實戰訊號判定
            is_bull_trend = (curr_p > ma20 > ma50 > ma200)
            
            if is_bull_trend and rvol >= 1.4 and cmf20 > 0.08:
                signal = "🔥 爆量突破 (主力點火)"
                score = 95
            elif is_bull_trend and cmf20 > 0.05:
                signal = "📈 多頭吸籌 (穩健上漲)"
                score = 80
            elif curr_p > ma50 and cmf20 > 0.12 and not is_bull_trend:
                signal = "🐳 底部暗池吸籌 (留意轉強)"
                score = 70
            elif curr_p < ma20 and cmf20 < -0.05:
                signal = "⚠️ 跌破月線 + 主力流出"
                score = 30
            else:
                signal = "👀 區間震盪 / 觀望"
                score = 50
                
            results.append({
                "代號": sym,
                "綜合評分": score,
                "實戰訊號": signal,
                "現價 ($)": round(curr_p, 2),
                "單日漲跌 (%)": round(pct_chg, 2),
                "RVOL (爆量倍數)": round(rvol, 2),
                "CMF (主力資金流)": round(cmf20, 3),
                "RSI (14)": round(rsi14, 1),
                "ATR 停損價 ($)": round(stop_loss_price, 2),
                "建議買進股數": suggested_shares,
                "日均成交額 (M$)": round(dollar_vol_m, 1),
                "_is_bull": is_bull_trend
            })
        except Exception:
            continue
            
    df_out = pd.DataFrame(results)
    if not df_out.empty:
        df_out = df_out.sort_values(by=["綜合評分", "CMF (主力資金流)"], ascending=[False, False])
    return df_out, raw_histories

col_btn1, col_btn2 = st.columns([1, 4])
with col_btn1:
    if st.button("🔄 立即強制刷新盤中數據", use_container_width=True):
        st.cache_data.clear()

with st.spinner("正在計算主力籌碼、均線趨勢與風控模型..."):
    df_scan, histories = scan_stocks(tickers, capital, risk_pct, atr_mult)

if not df_scan.empty:
    # 執行篩選過濾
    if only_uptrend:
        df_scan = df_scan[df_scan["_is_bull"] == True]
    if only_inflow:
        df_scan = df_scan[df_scan["CMF (主力資金流)"] > 0]
        
    display_df = df_scan.drop(columns=["_is_bull"])
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "綜合評分": st.column_config.ProgressColumn("強度評分", format="%d", min_value=0, max_value=100),
            "單日漲跌 (%)": st.column_config.NumberColumn("漲跌幅 (%)", format="%+.2f%%"),
            "CMF (主力資金流)": st.column_config.NumberColumn("CMF 資金流", help=">0 代表主力資金淨流入，>0.1 代表強烈吸籌"),
            "RVOL (爆量倍數)": st.column_config.NumberColumn("RVOL 量比", help=">1.5 代表今日成交量明顯放大"),
            "ATR 停損價 ($)": st.column_config.NumberColumn("動態停損價 ($)", help=f"現價減去 {atr_mult} 倍 ATR 波幅"),
            "建議買進股數": st.column_config.NumberColumn("風控建議股數", help=f"若跌破停損價，最多只會賠總本金的 {risk_pct}%")
        }
    )
else:
    st.warning("查無符合條件的股票，請調整左側篩選器或確認股票代號。")

st.divider()

# ==========================================
# 模組三：單一標的深度 K 線與主力籌碼圖
# ==========================================
st.subheader("📊 模組三：個股 K 線、均線與主力資金流向圖")

if histories:
    selected_ticker = st.selectbox("選擇要深度剖析的標的：", list(histories.keys()))
    df_plot = histories[selected_ticker].tail(120) # 取近半年 (約120個交易日) 方便手機觀看
    
    # 計算繪圖用均線與 CMF
    df_plot['MA20'] = df_plot['Close'].rolling(20).mean()
    df_plot['MA50'] = df_plot['Close'].rolling(50).mean()
    mfm = ((df_plot['Close'] - df_plot['Low']) - (df_plot['High'] - df_plot['Close'])) / (df_plot['High'] - df_plot['Low'] + 1e-9)
    df_plot['CMF'] = (mfm * df_plot['Volume']).rolling(20).sum() / (df_plot['Volume'].rolling(20).sum() + 1e-9)
    
    # 建立三層子圖：K線+均線 / 成交量 / CMF主力資金流
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, 
        vertical_spacing=0.04, 
        row_heights=[0.55, 0.2, 0.25],
        subplot_titles=(f"{selected_ticker} 日 K 線與均線 (20MA / 50MA)", "成交量 (Volume)", "主力資金流向 (20日 CMF)")
    )
    
    # 1. K線與均線
    fig.add_trace(go.Candlestick(
        x=df_plot.index, open=df_plot['Open'], high=df_plot['High'],
        low=df_plot['Low'], close=df_plot['Close'], name="K線"
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA20'], line=dict(color='orange', width=1.5), name='20MA (月線)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA50'], line=dict(color='cyan', width=1.5), name='50MA (季線)'), row=1, col=1)
    
    # 2. 成交量柱狀圖
    vol_colors = ['#ef5350' if c < o else '#26a69a' for c, o in zip(df_plot['Close'], df_plot['Open'])]
    fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=vol_colors, name="成交量"), row=2, col=1)
    
    # 3. CMF 資金流面積圖
    cmf_colors = ['#26a69a' if v >= 0 else '#ef5350' for v in df_plot['CMF']]
    fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['CMF'], marker_color=cmf_colors, name="CMF 資金流"), row=3, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="gray", row=3, col=1)
    
    fig.update_layout(height=700, xaxis_rangeslider_visible=False, template="plotly_dark", showlegend=True)
    st.plotly_chart(fig, use_container_width=True)
