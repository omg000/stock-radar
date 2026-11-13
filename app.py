import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, date
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 網頁基本設定
st.set_page_config(page_title="美股量化實戰雷達 3.0", page_icon="🦅", layout="wide")

st.title("美股量化實戰追蹤系統 3.0")
st.caption("直覺觸控縮放 K 線 ｜ 財報日避雷預警 ｜ 機構目標價與基本面 ｜ 華爾街即時新聞中心")

# ==========================================
# 側邊欄：參數、自動刷新與風控設定
# ==========================================
st.sidebar.header("系統與自動刷新設定")

auto_refresh = st.sidebar.toggle("開啟盤中自動更新", value=False, help="開啟後系統將定時自動抓取最新報價與K線")
refresh_sec = st.sidebar.selectbox("自動更新頻率 (秒)", [60, 180, 300], index=1)

default_tickers = "NVDA, AAPL, MSFT, AMZN, META, TSLA, PLTR, AMD, AVGO, CRWD, LLY, SMCI, COIN"
user_tickers = st.sidebar.text_area("監控標的清單 (逗號分隔)", default_tickers, height=90)
tickers = [t.strip().upper() for t in user_tickers.split(",") if t.strip()]

st.sidebar.subheader("量化風控計算器")
capital = st.sidebar.number_input("總投資本金 (USD)", min_value=500, value=10000, step=500)
risk_pct = st.sidebar.slider("單筆最大承受虧損 (%)", min_value=0.5, max_value=5.0, value=1.5, step=0.5)
atr_mult = st.sidebar.slider("ATR 停損寬度 (倍)", min_value=1.0, max_value=4.0, value=2.0, step=0.5)

st.sidebar.subheader("快速過濾")
min_score = st.sidebar.slider("最低強度評分門檻", 0, 100, 0, 5)
only_inflow = st.sidebar.checkbox("只顯示「主力資金淨流入 (CMF > 0)」", value=False)

# ==========================================
# 輔助函數：抓取財報日期、基本面與即時新聞
# ==========================================
@st.cache_data(ttl=1800) # 快取 30 分鐘，避免拖慢盤中速度
def get_earnings_and_fundamentals(sym):
    res = {
        "earnings_str": "未知",
        "days_to_earnings": 999,
        "pe_forward": None,
        "peg": None,
        "rev_growth": None,
        "profit_margin": None,
        "target_price": None,
        "recommendation": "N/A",
        "market_cap_b": None
    }
    try:
        tk = yf.Ticker(sym)
        # 1. 取得下次財報日
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
                    
        # 2. 取得基本面與華爾街目標價
        info = tk.info
        if isinstance(info, dict):
            res["pe_forward"] = info.get("forwardPE")
            res["peg"] = info.get("pegRatio")
            res["rev_growth"] = info.get("revenueGrowth")
            res["profit_margin"] = info.get("profitMargins")
            res["target_price"] = info.get("targetMeanPrice")
            res["recommendation"] = str(info.get("recommendationKey", "N/A")).upper()
            mcap = info.get("marketCap")
            if mcap:
                res["market_cap_b"] = round(mcap / 1e9, 1)
    except Exception:
        pass
    return res

@st.cache_data(ttl=300) # 新聞快取 5 分鐘
def fetch_realtime_news(sym):
    news_items = []
    # 優先從 Yahoo Finance API 抓取結構化新聞
    try:
        raw_news = yf.Ticker(sym).news
        for item in raw_news[:8]:
            content = item.get("content", item)
            title = content.get("title")
            # 解析連結
            link = ""
            if "canonicalUrl" in content and isinstance(content["canonicalUrl"], dict):
                link = content["canonicalUrl"].get("url", "")
            elif "clickThroughUrl" in content and isinstance(content["clickThroughUrl"], dict):
                link = content["clickThroughUrl"].get("url", "")
            else:
                link = content.get("link", "")
            # 解析機構與時間
            provider = content.get("provider", {}).get("displayName", item.get("publisher", "Yahoo Finance"))
            pub_time = content.get("pubDate", item.get("providerPublishTime", ""))
            if isinstance(pub_time, (int, float)):
                pub_time = datetime.fromtimestamp(pub_time).strftime('%m-%d %H:%M')
            elif isinstance(pub_time, str) and len(pub_time) >= 16:
                pub_time = pub_time[:16].replace("T", " ")
            if title:
                news_items.append({"title": title, "link": link, "publisher": provider, "time": pub_time})
    except Exception:
        pass
        
    # 備援機制：透過 Google News RSS 抓取即時財經新聞
    if not news_items:
        try:
            query = "US+stock+market+Wall+Street" if sym in ["SPY", "QQQ"] else f"{sym}+stock+news"
            url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                root = ET.fromstring(response.read())
                for item in root.findall('.//item')[:8]:
                    news_items.append({
                        "title": item.find('title').text if item.find('title') is not None else "",
                        "link": item.find('link').text if item.find('link') is not None else "",
                        "publisher": item.find('source').text if item.find('source') is not None else "Financial News",
                        "time": item.find('pubDate').text[:16] if item.find('pubDate') is not None else ""
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

    with col_metrics:
        c1, c2, c3 = st.columns(3)
        spy, qqq, sox, iwm, tnx = m_data["SPY"], m_data["QQQ"], m_data["^SOX"], m_data["IWM"], m_data["^TNX"]
        
        c1.metric("標普 500 (SPY 大盤)", f"${spy['curr']:.2f}", f"{spy['chg_pct']:+.2f}%")
        c2.metric("納斯達克 (QQQ 科技股)", f"${qqq['curr']:.2f}", f"{qqq['chg_pct']:+.2f}%")
        c3.metric("費城半導體 (^SOX AI硬體)", f"{sox['curr']:.1f}", f"{sox['chg_pct']:+.2f}%")
        
        c4, c5, c6 = st.columns(3)
        c4.metric("羅素 2000 (IWM 中小型股)", f"${iwm['curr']:.2f}", f"{iwm['chg_pct']:+.2f}%")
        c5.metric("10年期美債殖利率 (^TNX)", f"{tnx['curr']:.2f}%", f"{tnx['chg_abs']:+.2f}", delta_color="inverse")
        
        with c6:
            st.markdown("##### 盤勢綜合診斷")
            if vix < 20 and spy['curr'] > spy['ma20'] and qqq['curr'] > qqq['ma20']:
                st.success("**🟢 多頭順風車**：大盤與科技股皆站穩月線且恐慌低，可積極操作高分強勢股。")
            elif vix >= 25 or spy['curr'] < spy['ma50']:
                st.error("**🔴 風險警戒區**：VIX 偏高或大盤跌破季線，建議保留現金、減少新開倉。")
            else:
                st.warning("**🟡 結構性震盪**：指數整理中，避免追高，鎖定「CMF > 0.1」主力護盤股。")
except Exception as e:
    st.warning(f"正在同步大盤宏觀數據... ({e})")

st.divider()

# ==========================================
# 模組二：100分制動態評分、財報避雷與主力籌碼表
# ==========================================
st.subheader("主力動向、財報預警")

@st.cache_data(ttl=120)
def scan_stocks_v3(ticker_list, total_cap, risk_p, atr_m):
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
            
            close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
            curr_p = float(close.iloc[-1])
            prev_p = float(close.iloc[-2])
            pct_chg = ((curr_p - prev_p) / prev_p) * 100
            
            # 均線、量比、CMF、RSI、ATR
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
            risk_per_share = curr_p - stop_loss_price
            suggested_shares = int((total_cap * (risk_p / 100.0)) // risk_per_share) if risk_per_share > 0 else 0

            # 100分制動態加權
            trend_pts = (12 if curr_p > ma20 else 0) + (10 if curr_p > ma50 else 0) + (10 if curr_p > ma200 else 0) + (8 if ma20 > ma50 > ma200 else 0)
            cmf_pts = int(((max(-0.25, min(0.25, cmf20)) + 0.25) / 0.50) * 30)
            rvol_pts = int(min(20, max(0, (rvol - 0.5) * 13))) if pct_chg >= 0 else int(max(0, 10 - (rvol - 0.8) * 10))
            rsi_pts = 10 if 50 <= rsi14 <= 72 else (6 if (40 <= rsi14 < 50 or 72 < rsi14 <= 80) else 2)
            total_score = int(min(100, max(5, trend_pts + cmf_pts + rvol_pts + rsi_pts)))
            
            # 取得財報日資訊
            f_info = get_earnings_and_fundamentals(sym)
            
            if 0 <= f_info["days_to_earnings"] <= 7:
                signal = "財報將至 (注意跳空風險)"
            elif total_score >= 80 and rvol >= 1.3:
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
                "下次財報日": f_info["earnings_str"],
                "現價 ($)": round(curr_p, 2),
                "單日漲跌 (%)": round(pct_chg, 2),
                "近20日走勢": close.tail(20).tolist(),
                "CMF 主力資金": round(cmf20, 3),
                "RVOL 量比": round(rvol, 2),
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

with st.spinner("正在運算多因子模型、主力籌碼與財報日曆..."):
    df_scan, histories = scan_stocks_v3(tickers, capital, risk_pct, atr_mult)

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
            "下次財報日": st.column_config.TextColumn("財報避雷針", help="財報公布前後常有劇烈跳空，14天內公布會亮起⚠️警示"),
            "近20日走勢": st.column_config.LineChartColumn("近20日趨勢線"),
            "單日漲跌 (%)": st.column_config.NumberColumn("漲跌幅 (%)", format="%+.2f%%"),
            "CMF 主力資金": st.column_config.NumberColumn("CMF 籌碼流", help=">0 代表主力買超吸籌，>0.1 為強烈買進"),
            "RVOL 量比": st.column_config.NumberColumn("RVOL 爆量倍數", help=">1.3 代表明顯放量")
        }
    )

st.divider()

# ==========================================
# 模組三：支援「雙指捏合縮放 / 單指拖曳」的 K 線看盤室
# ==========================================
st.subheader("K 線")
st.caption("操作小撇步：在 K 線圖上直接用「單指左右滑動」可平移時間軸，用「雙指張開/捏合（或滑鼠滾輪）」可自由放大縮小！快點兩下即可恢復預設大小。")

if histories:
    c_sel1, c_sel2 = st.columns([1, 2])
    with c_sel1:
        selected_ticker = st.selectbox("選擇深度剖析標的：", list(histories.keys()))
    with c_sel2:
        timeframe = st.radio(
            "選擇 K 線週期：",
            ["波段日 K 線 (含 20/50/200 均線 + CMF 籌碼)", "盤中 5 分鐘 K 線 (含當日重置 VWAP 機構均價)", "盤中 15 分鐘 K 線 (近1個月短波段)"],
            horizontal=True
        )
        
    # 觸控與滾輪縮放的核心設定
    touch_chart_config = {
        'scrollZoom': True,      # 開啟雙指捏合縮放與滑鼠滾輪縮放
        'displayModeBar': True,  # 顯示右上角工具列
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
        
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        # 關鍵修正：dragmode='pan' 讓手指滑動變成平移而非拉框框，fixedrange=False 允許自由縮放
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
            
            # 關鍵精準度修正：VWAP 必須「每個交易日開盤重新歸零計算」
            df_intra['Date'] = df_intra.index.date
            df_intra['TypPrice'] = (df_intra['High'] + df_intra['Low'] + df_intra['Close']) / 3
            df_intra['VP'] = df_intra['TypPrice'] * df_intra['Volume']
            df_intra['VWAP'] = df_intra.groupby('Date')['VP'].cumsum() / (df_intra.groupby('Date')['Volume'].cumsum() + 1e-9)
            
            time_labels = df_intra.index.strftime('%m-%d %H:%M')
            
            fig_intra = make_subplots(
                rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.72, 0.28],
                subplot_titles=(f"{selected_ticker} 盤中 {interval_str} K 線 (20EMA 與 每日重置機構 VWAP)", "盤中分時成交量")
            )
            fig_intra.add_trace(go.Candlestick(
                x=time_labels, open=df_intra['Open'], high=df_intra['High'],
                low=df_intra['Low'], close=df_intra['Close'], name=f"{interval_str} K線"
            ), row=1, col=1)
            fig_intra.add_trace(go.Scatter(x=time_labels, y=df_intra['EMA20'], line=dict(color='#FFA726', width=1.5), name='20 EMA'), row=1, col=1)
            fig_intra.add_trace(go.Scatter(x=time_labels, y=df_intra['VWAP'], line=dict(color='#FFEE58', width=1.5, dash='dash'), name='當日 VWAP (機構均價線)'), row=1, col=1)
            
            v_colors = ['#ef5350' if c < o else '#26a69a' for c, o in zip(df_intra['Close'], df_intra['Open'])]
            fig_intra.add_trace(go.Bar(x=time_labels, y=df_intra['Volume'], marker_color=v_colors, name="分時量"), row=2, col=1)
            
            fig_intra.update_layout(height=620, xaxis_rangeslider_visible=False, template="plotly_dark", dragmode="pan")
            fig_intra.update_yaxes(fixedrange=False)
            st.plotly_chart(fig_intra, use_container_width=True, config=touch_chart_config)

st.divider()

# ==========================================
# 個股財報體質、華爾街目標價 ＆ 即時新聞中心
# ==========================================
st.subheader(f"模組四：{selected_ticker} 財報基本面體質 ＆ 華爾街即時新聞")

col_fund, col_news = st.columns([1.2, 1.8])

with col_fund:
    st.markdown(f"#### {selected_ticker} 財報與機構評級卡片")
    f_data = get_earnings_and_fundamentals(selected_ticker)
    curr_price_sel = float(histories[selected_ticker]['Close'].iloc[-1])
    
    f1, f2 = st.columns(2)
    f1.metric("下次財報公布日", f_data["earnings_str"])
    
    if f_data["target_price"]:
        upside = ((f_data["target_price"] - curr_price_sel) / curr_price_sel) * 100
        f2.metric("華爾街平均目標價", f"${f_data['target_price']:.2f}", f"{upside:+.1f}% 潛在空間")
    else:
        f2.metric("華爾街平均目標價", "N/A")
        
    f3, f4 = st.columns(2)
    f3.metric("預估本益比 (Forward P/E)", f"{f_data['pe_forward']:.1f}x" if f_data["pe_forward"] else "N/A")
    f4.metric("分析師共識評級", f_data["recommendation"])
    
    f5, f6 = st.columns(2)
    f5.metric("營收年增率 (YoY)", f"{f_data['rev_growth']*100:+.1f}%" if f_data["rev_growth"] else "N/A")
    f6.metric("淨利率 (Profit Margin)", f"{f_data['profit_margin']*100:.1f}%" if f_data["profit_margin"] else "N/A")

    st.info("**財報實戰守則**：若距離財報公布不到 **7 天**，即使技術面滿分也建議先減碼或觀望，避免財報開獎瞬間發生無法停損的跳空大跌（Earnings Gap Risk）。")

with col_news:
    news_tab1, news_tab2 = st.tabs([f"{selected_ticker} 專屬即時外電", "華爾街大盤總經頭條 (SPY/QQQ)"])
    
    with news_tab1:
        ticker_news = fetch_realtime_news(selected_ticker)
        if ticker_news:
            for n in ticker_news:
                st.markdown(f"**• [{n['title']}]({n['link']})**  \n<span style='color:gray;font-size:12px;'>{n['publisher']} ｜ {n['time']}</span>", unsafe_allow_html=True)
        else:
            st.write("暫無最新個股外電。")
            
    with news_tab2:
        macro_news = fetch_realtime_news("SPY")
        if macro_news:
            for n in macro_news:
                st.markdown(f"**• [{n['title']}]({n['link']})**  \n<span style='color:gray;font-size:12px;'>{n['publisher']} ｜ {n['time']}</span>", unsafe_allow_html=True)
        else:
            st.write("暫無最新大盤頭條。")

# 觸發盤中自動更新機制
if auto_refresh:
    time.sleep(refresh_sec)
    st.cache_data.clear()
    st.rerun()
