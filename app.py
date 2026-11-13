import time
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 網頁基本設定
st.set_page_config(page_title="美股量化實戰雷達 2.0", page_icon="🦅", layout="wide")

st.title("美股量化實戰追蹤系統 2.0")
st.caption("全自動盤中監控 ｜ VIX 情緒儀表板 ｜ 100分制動態權重評分 ｜ 盤中分K / 波段日K 雙模看盤")

# ==========================================
# 側邊欄：參數、自動刷新與風控設定
# ==========================================
st.sidebar.header("系統與自動刷新設定")

auto_refresh = st.sidebar.toggle("開啟盤中自動更新", value=False, help="開啟後系統將定時自動抓取最新報價與K線")
refresh_sec = st.sidebar.selectbox("自動更新頻率 (秒)", [60, 180, 300], index=1)

default_tickers = "NVDA, AAPL, MSFT, AMZN, META, TSLA, PLTR, AMD, AVGO, CRWD, LLY, SMCI, COIN"
user_tickers = st.sidebar.text_area("📋 監控標的清單 (逗號分隔)", default_tickers, height=90)
tickers = [t.strip().upper() for t in user_tickers.split(",") if t.strip()]

st.sidebar.subheader("量化風控計算器")
capital = st.sidebar.number_input("總投資本金 (USD)", min_value=500, value=10000, step=500)
risk_pct = st.sidebar.slider("單筆最大承受虧損 (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.5)
atr_mult = st.sidebar.slider("ATR 停損寬度 (倍)", min_value=1.0, max_value=4.0, value=2.0, step=0.5)

st.sidebar.subheader("快速過濾")
min_score = st.sidebar.slider("最低強度評分門檻", 0, 100, 0, 5)
only_inflow = st.sidebar.checkbox("只顯示「主力資金淨流入 (CMF > 0)」", value=False)

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
                curr = float(s.iloc[-1])
                prev = float(s.iloc[-2])
                chg_pct = ((curr - prev) / prev) * 100
                chg_abs = curr - prev
                ma20 = float(s.rolling(20).mean().iloc[-1])
                ma50 = float(s.rolling(50).mean().iloc[-1])
                metrics[sym] = {
                    "curr": curr, "chg_pct": chg_pct, "chg_abs": chg_abs,
                    "ma20": ma20, "ma50": ma50
                }
    return metrics

try:
    m_data = get_macro_dashboard()
    vix = m_data["^VIX"]["curr"]
    vix_diff = m_data["^VIX"]["chg_abs"]
    
    col_gauge, col_metrics = st.columns([1.3, 2.7])
    
    # 左側：VIX 視覺化汽車儀表板
    with col_gauge:
        if vix < 15:
            vix_status = "🟢 極度樂觀 (留意追高風險)"
        elif vix < 20:
            vix_status = "🟢 穩定偏多 (適合順勢做多)"
        elif vix < 30:
            vix_status = "🟠 警戒震盪 (縮小倉位/買黑不買紅)"
        else:
            vix_status = "🔴 極度恐慌 (嚴控風險/留意底部反轉)"
            
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=vix,
            delta={'reference': vix - vix_diff, 'increasing': {'color': "#ef5350"}, 'decreasing': {'color': "#26a69a"}},
            title={'text': f"<b>VIX 恐慌指數</b><br><span style='font-size:13px;color:gray'>{vix_status}</span>"},
            gauge={
                'axis': {'range': [10, 45], 'tickwidth': 1},
                'bar': {'color': "white", 'thickness': 0.25},
                'steps': [
                    {'range': [10, 15], 'color': "rgba(38, 166, 154, 0.45)"},
                    {'range': [15, 20], 'color': "rgba(102, 187, 106, 0.35)"},
                    {'range': [20, 30], 'color': "rgba(255, 167, 38, 0.45)"},
                    {'range': [30, 45], 'color': "rgba(239, 83, 80, 0.55)"}
                ],
                'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 30}
            }
        ))
        fig_gauge.update_layout(height=240, margin=dict(l=20, r=20, t=50, b=10), template="plotly_dark")
        st.plotly_chart(fig_gauge, use_container_width=True)

    # 右側：五大核心宏觀指標與白話解讀
    with col_metrics:
        c1, c2, c3 = st.columns(3)
        spy = m_data["SPY"]
        qqq = m_data["QQQ"]
        sox = m_data["^SOX"]
        iwm = m_data["IWM"]
        tnx = m_data["^TNX"]
        
        c1.metric("標普 500 (SPY 大盤)", f"${spy['curr']:.2f}", f"{spy['chg_pct']:+.2f}%", 
                  help="美股整體大盤基準，站上 20MA 代表短線偏多")
        c2.metric("納斯達克 (QQQ 科技股)", f"${qqq['curr']:.2f}", f"{qqq['chg_pct']:+.2f}%", 
                  help="大型科技成長股風向球")
        c3.metric("費城半導體 (^SOX AI硬體)", f"{sox['curr']:.1f}", f"{sox['chg_pct']:+.2f}%", 
                  help="NVDA、AVGO、AMD 等半導體族群溫度計")
        
        c4, c5, c6 = st.columns(3)
        c4.metric("羅素 2000 (IWM 中小型股)", f"${iwm['curr']:.2f}", f"{iwm['chg_pct']:+.2f}%", 
                  help="衡量市場廣度：若 IWM 跟漲代表資金百花齊放，若只漲 QQQ 不漲 IWM 代表資金僅集中權值股")
        c5.metric("10年期美債殖利率 (^TNX)", f"{tnx['curr']:.2f}%", f"{tnx['chg_abs']:+.2f}", delta_color="inverse",
                  help="市場無風險利率基準：若急速飆升（超過 4.5%），科技股估值容易承壓回檔")
        
        with c6:
            st.markdown("##### 盤勢綜合診斷")
            if vix < 20 and spy['curr'] > spy['ma20'] and qqq['curr'] > qqq['ma20']:
                st.success("**🟢 多頭順風車**：大盤與科技股皆站穩月線且恐慌指數低，可積極操作高分強勢股。")
            elif vix >= 25 or spy['curr'] < spy['ma50']:
                st.error("**🔴 風險警戒區**：VIX 偏高或大盤跌破季線，機構正在避險，建議保留現金、減少新開倉。")
            else:
                st.warning("**🟡 結構性震盪**：指數整理中，避免追高，建議鎖定「CMF > 0.1」有主力護盤的個股。")

    with st.expander(" 點此查看：如何判讀 VIX 恐慌指數與大盤指標？（新手必讀）"):
        st.markdown("""
        * **VIX 恐慌指數區間意義**：
          * **10 ~ 15（極度樂觀）**：市場毫無戒心，通常處於大波段高點區，此時不宜過度追高（防範突發回檔）。
          * **15 ~ 20（健康常態）**：最舒服的多頭慢牛環境，適合順勢操作強勢突破股。
          * **20 ~ 30（恐慌升溫）**：市場出現利空消息、波動放大，應縮小每筆下單部位。
          * **30 以上（極度恐慌）**：市場非理性拋售，若 VIX 衝破 30 後開始彎頭向下，往往是絕佳的中長線抄底機會！
        * **為什麼要看 IWM（中小型股）與 ^TNX（美債殖利率）？**
          * 當 **SPY 與 IWM 同步上漲**，代表主力資金全面進場，買突破的勝率最高；反之若 **^TNX 殖利率突然暴漲**，主力通常會先拋售高估值的科技股。
        """)
except Exception as e:
    st.warning(f"正在同步大盤宏觀數據... ({e})")

st.divider()

# ==========================================
# 模組二：100分制動態評分、主力籌碼與迷你走勢表
# ==========================================
st.subheader("主力動向")

@st.cache_data(ttl=120)
def scan_stocks_v2(ticker_list, total_cap, risk_p, atr_m):
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
            
            # 2. 相對成交量 (RVOL)
            avg_vol20 = float(vol.rolling(20).mean().iloc[-1])
            rvol = float(vol.iloc[-1]) / avg_vol20 if avg_vol20 > 0 else 1.0
            
            # 3. 蔡金資金流向 (CMF 20日)
            mfm = ((close - low) - (high - close)) / (high - low + 1e-9)
            mfv = mfm * vol
            cmf20 = float(mfv.rolling(20).sum().iloc[-1] / (vol.rolling(20).sum().iloc[-1] + 1e-9))
            
            # 4. RSI (14日)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss + 1e-9)
            rsi14 = float(100 - (100 / (1 + rs.iloc[-1])))
            
            # 5. ATR 停損與倉位計算
            tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
            stop_loss_price = curr_p - (atr_m * atr14)
            risk_per_share = curr_p - stop_loss_price
            max_loss_usd = total_cap * (risk_p / 100.0)
            suggested_shares = int(max_loss_usd // risk_per_share) if risk_per_share > 0 else 0

            # ==========================================
            # 全新 100 分制動態加權評分引擎 (解決通通50分的問題)
            # ==========================================
            # (A) 趨勢得分 (滿分 40 分)
            trend_pts = 0
            if curr_p > ma20: trend_pts += 12
            if curr_p > ma50: trend_pts += 10
            if curr_p > ma200: trend_pts += 10
            if ma20 > ma50 > ma200: trend_pts += 8
            
            # (B) 主力籌碼 CMF 得分 (滿分 30 分，將 -0.25 ~ +0.25 映射到 0 ~ 30 分)
            cmf_clamped = max(-0.25, min(0.25, cmf20))
            cmf_pts = int(((cmf_clamped + 0.25) / 0.50) * 30)
            
            # (C) 動能爆量 RVOL 得分 (滿分 20 分)
            if pct_chg >= 0:
                rvol_pts = int(min(20, max(0, (rvol - 0.5) * 13)))
            else:
                # 若下跌還爆量，扣減動能分
                rvol_pts = int(max(0, 10 - (rvol - 0.8) * 10))
                
            # (D) RSI 動能健康度 (滿分 10 分：50~70 最強勢給滿分)
            if 50 <= rsi14 <= 72:
                rsi_pts = 10
            elif 40 <= rsi14 < 50 or 72 < rsi14 <= 80:
                rsi_pts = 6
            else:
                rsi_pts = 2
                
            total_score = int(min(100, max(5, trend_pts + cmf_pts + rvol_pts + rsi_pts)))
            
            # 根據細緻分數與籌碼給予實戰標籤
            if total_score >= 80 and rvol >= 1.3:
                signal = "主力點火突破 (極強)"
            elif total_score >= 70:
                signal = "多頭穩健推進 (偏多)"
            elif cmf20 >= 0.10 and curr_p < ma20:
                signal = "回檔暗池吸籌 (逢低留意)"
            elif total_score <= 35:
                signal = "空頭走弱 / 主力撤退"
            else:
                signal = "區間整理 (等待方向)"
                
            results.append({
                "代號": sym,
                "強度評分": total_score,
                "實戰訊號": signal,
                "現價 ($)": round(curr_p, 2),
                "單日漲跌 (%)": round(pct_chg, 2),
                "近20日走勢": close.tail(20).tolist(),
                "CMF 主力資金": round(cmf20, 3),
                "RVOL 量比": round(rvol, 2),
                "RSI (14)": round(rsi14, 1),
                "ATR 停損價 ($)": round(stop_loss_price, 2),
                "建議買進股數": suggested_shares
            })
        except Exception:
            continue
            
    df_out = pd.DataFrame(results)
    if not df_out.empty:
        df_out = df_out.sort_values(by=["強度評分", "CMF 主力資金"], ascending=[False, False])
    return df_out, raw_histories

col_b1, col_b2 = st.columns([1, 4])
with col_b1:
    if st.button("立即手動更新報價", use_container_width=True):
        st.cache_data.clear()

with st.spinner("正在運算 100 分制多因子模型與主力籌碼..."):
    df_scan, histories = scan_stocks_v2(tickers, capital, risk_pct, atr_mult)

if not df_scan.empty:
    df_filtered = df_scan[df_scan["強度評分"] >= min_score]
    if only_inflow:
        df_filtered = df_filtered[df_filtered["CMF 主力資金"] > 0]
        
    st.dataframe(
        df_filtered,
        use_container_width=True,
        hide_index=True,
        column_config={
            "強度評分": st.column_config.ProgressColumn(
                "綜合強度 (0-100)", format="%d 分", min_value=0, max_value=100,
                help="結合：均線趨勢(40%) + CMF主力籌碼(30%) + RVOL量能(20%) + RSI位置(10%)"
            ),
            "近20日走勢": st.column_config.LineChartColumn("近20日趨勢線"),
            "單日漲跌 (%)": st.column_config.NumberColumn("漲跌幅 (%)", format="%+.2f%%"),
            "CMF 主力資金": st.column_config.NumberColumn("CMF 籌碼流", help=">0 代表主力買超吸籌，>0.1 為強烈買進；<0 代表主力出貨"),
            "RVOL 量比": st.column_config.NumberColumn("RVOL 爆量倍數", help="今日成交量除以20日均量，>1.3 代表明顯放量")
        }
    )

st.divider()

# ==========================================
# 模組三：雙模式 K 線看盤室 (支援盤中分K + 波段日K)
# ==========================================
st.subheader(" K 線（支援盤中即時分 K ＆ 波段日 K）")

if histories:
    c_sel1, c_sel2 = st.columns([1, 2])
    with c_sel1:
        selected_ticker = st.selectbox("選擇看盤標的：", list(histories.keys()))
    with c_sel2:
        timeframe = st.radio(
            "選擇 K 線週期：",
            ["波段日 K 線 (含 20/50/200 均線 + CMF 籌碼)", "⚡ 盤中 5 分鐘 K 線 (近5日當沖/盤中盯盤)", "⚡ 盤中 15 分鐘 K 線 (近1個月短波段)"],
            horizontal=True
        )
        
    if "波段日 K" in timeframe:
        df_plot = histories[selected_ticker].tail(130).copy()
        df_plot['MA20'] = df_plot['Close'].rolling(20).mean()
        df_plot['MA50'] = df_plot['Close'].rolling(50).mean()
        df_plot['MA200'] = df_plot['Close'].rolling(200).mean()
        mfm = ((df_plot['Close'] - df_plot['Low']) - (df_plot['High'] - df_plot['Close'])) / (df_plot['High'] - df_plot['Low'] + 1e-9)
        df_plot['CMF'] = (mfm * df_plot['Volume']).rolling(20).sum() / (df_plot['Volume'].rolling(20).sum() + 1e-9)
        
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.58, 0.18, 0.24],
            subplot_titles=(f"{selected_ticker} 日 K 線 (20MA / 50MA / 200MA)", "成交量 (Volume)", "CMF 主力資金流向 (綠柱吸籌 / 紅柱出貨)")
        )
        fig.add_trace(go.Candlestick(
            x=df_plot.index, open=df_plot['Open'], high=df_plot['High'],
            low=df_plot['Low'], close=df_plot['Close'], name="日K線"
        ), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA20'], line=dict(color='#FFA726', width=1.5), name='20MA (月線)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA50'], line=dict(color='#29B6F6', width=1.5), name='50MA (季線)'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MA200'], line=dict(color='#AB47BC', width=1.5, dash='dot'), name='200MA (年線)'), row=1, col=1)
        
        vol_colors = ['#ef5350' if c < o else '#26a69a' for c, o in zip(df_plot['Close'], df_plot['Open'])]
        fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color=vol_colors, name="成交量"), row=2, col=1)
        
        cmf_colors = ['#26a69a' if v >= 0 else '#ef5350' for v in df_plot['CMF']]
        fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['CMF'], marker_color=cmf_colors, name="CMF 資金流"), row=3, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="gray", row=3, col=1)
        
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])]) # 隱藏週末空白
        fig.update_layout(height=720, xaxis_rangeslider_visible=False, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        # 抓取盤中分 K 資料
        interval_str = "5m" if "5 分鐘" in timeframe else "15m"
        period_str = "5d" if interval_str == "5m" else "1mo"
        
        with st.spinner(f"正在載入 {selected_ticker} 的 {interval_str} 盤中即時 K 線..."):
            df_intra = yf.download(selected_ticker, period=period_str, interval=interval_str, progress=False)
            if isinstance(df_intra.columns, pd.MultiIndex):
                df_intra.columns = df_intra.columns.get_level_values(0)
            df_intra = df_intra.dropna().tail(120)
            
            df_intra['EMA20'] = df_intra['Close'].ewm(span=20).mean()
            df_intra['VWAP'] = (df_intra['Volume'] * (df_intra['High'] + df_intra['Low'] + df_intra['Close']) / 3).cumsum() / df_intra['Volume'].cumsum()
            
            # 轉為字串座標軸，完美消除盤後與週末斷層空白
            time_labels = df_intra.index.strftime('%m-%d %H:%M')
            
            fig_intra = make_subplots(
                rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.72, 0.28],
                subplot_titles=(f"{selected_ticker} 盤中 {interval_str} K 線 (含 20EMA 與 VWAP 均價線)", "盤中分時成交量")
            )
            fig_intra.add_trace(go.Candlestick(
                x=time_labels, open=df_intra['Open'], high=df_intra['High'],
                low=df_intra['Low'], close=df_intra['Close'], name=f"{interval_str} K線"
            ), row=1, col=1)
            fig_intra.add_trace(go.Scatter(x=time_labels, y=df_intra['EMA20'], line=dict(color='#FFA726', width=1.5), name='20 EMA'), row=1, col=1)
            fig_intra.add_trace(go.Scatter(x=time_labels, y=df_intra['VWAP'], line=dict(color='#FFEE58', width=1.5, dash='dash'), name='VWAP (機構當沖均價)'), row=1, col=1)
            
            v_colors = ['#ef5350' if c < o else '#26a69a' for c, o in zip(df_intra['Close'], df_intra['Open'])]
            fig_intra.add_trace(go.Bar(x=time_labels, y=df_intra['Volume'], marker_color=v_colors, name="分時量"), row=2, col=1)
            
            fig_intra.update_layout(height=620, xaxis_rangeslider_visible=False, template="plotly_dark")
            st.plotly_chart(fig_intra, use_container_width=True)

# 觸發盤中自動更新機制
if auto_refresh:
    time.sleep(refresh_sec)
    st.cache_data.clear()
    st.rerun()
