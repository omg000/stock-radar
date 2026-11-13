import streamlit as st
import yfinance as yf
import pandas as pd

# 設定網頁標題與排版
st.set_page_config(page_title="美股追蹤雷達", layout="centered")

st.title("📱 我的美股動能追蹤雷達")
st.write("這是你的專屬行動版股市監控看板，隨時隨地都可以用手機查看！")

# 讓使用者自訂輸入想看的股票代號
default_tickers = "NVDA, AAPL, TSLA, MSFT, PLTR, AMD"
user_input = st.text_input("輸入美股代號（用逗號隔開）", default_tickers)
tickers = [t.strip().upper() for t in user_input.split(",")]

if st.button("🚀 開始掃描數據", use_container_width=True):
    with st.spinner("正在從雲端抓取最新報價..."):
        try:
            # 抓取近 5 天資料
            data = yf.download(tickers, period="5d", interval="1d", progress=False)
            
            if isinstance(data.columns, pd.MultiIndex):
                close_df = data['Close']
            else:
                close_df = data[['Close']]
                if len(tickers) == 1:
                    close_df.columns = tickers

            results = []
            for ticker in tickers:
                if ticker in close_df.columns:
                    s = close_df[ticker].dropna()
                    if len(s) >= 2:
                        curr = s.iloc[-1]
                        prev = s.iloc[-2]
                        change = ((curr - prev) / prev) * 100
                        results.append({
                            "標的": ticker,
                            "現價 ($)": round(float(curr), 2),
                            "漲跌幅 (%)": round(float(change), 2)
                        })
            
            if results:
                df_res = pd.DataFrame(results)
                st.success("✅ 數據載入成功！")
                st.dataframe(df_res, use_container_width=True)
            else:
                st.warning("⚠️ 找不到對應的數據，請確認代號是否正確。")
                
        except Exception as e:
            st.error(f"發生錯誤: {e}")

st.info("💡 提示：你可以將這個網頁釘選到手機桌面，隨時像 App 一樣打開！")