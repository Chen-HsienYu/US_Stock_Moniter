import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
import requests  # 必須要有這個
from datetime import datetime

# ==========================================
# 1. 全局配置
# ==========================================
st.set_page_config(page_title="Mark 智能戰情室", layout="wide")

st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 3rem;}
        section[data-testid="stSidebar"] {width: 320px !important;} 
        div.stButton > button {width: 100%; border-radius: 8px;}
        .stDataFrame {margin-bottom: 2rem;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. Session State
# ==========================================
if 'sector_data' not in st.session_state:
    st.session_state.sector_data = {
        "美股巨頭": ["NVDA", "TSLA", "GOOGL", "MSFT", "AMZN", "META", "AAPL", "ORCL", "PLTR"],
        "晶片半導體": ["NVDA", "INTC", "SMCI", "NVTS", "AMD", "TSM", "AVGO", "QCOM"],
        "量子運算": ["RGTI", "QUBT", "IONQ", "QBTS", "LAES"],
        "機器人": ["TSLA", "PATH", "PLTR", "SERV"],
        "核能與能源": ["OKLO", "SMR", "CRML", "EOSE", "LAC", "MP", "NB", "UAMY", "USAR", "UUUU"],
        "加密貨幣": ["COIN", "MSTR", "MARA", "HUT", "CLSK", "APLD", "BITF", "BMNR", "CIFR", "IREN", "RIOT", "SBET"],
        "太空股": ["ASTS", "RKLB", "DXYZ", "FJET", "LUNR", "RDW", "SIDU"],
        "無人機股": ["ONDS", "RCAT", "UMAC"],
        "AI應用": ["SOUN", "PLTR"],
        "現有倉位": ["APLD", "CLSK"]
    }

def add_ticker():
    new_t = st.session_state.new_ticker_input.strip().upper()
    target_sector = st.session_state.target_sector_select
    if new_t:
        if new_t not in st.session_state.sector_data[target_sector]:
            st.session_state.sector_data[target_sector].insert(0, new_t)
            st.toast(f"成功將 {new_t} 加入 [{target_sector}]", icon="✅")
        else:
            st.toast(f"{new_t} 已經在 [{target_sector}] 裡面了", icon="⚠️")
        st.session_state.new_ticker_input = ""

# ==========================================
# 3. 側邊欄
# ==========================================
with st.sidebar:
    st.header("控制中心")
    st.subheader("系統狀態")
    auto_refresh = st.toggle("啟動自動刷新", value=True)
    manual_refresh = st.button("🔄 立即手動刷新", type="primary")
    with st.expander("設定刷新頻率"):
        refresh_rate = st.slider("秒數", 10, 300, 15)
    
    st.divider()
    st.subheader("新增股票")
    st.selectbox("選擇目標板塊", options=st.session_state.sector_data.keys(), key="target_sector_select")
    st.text_input("輸入代碼按 Enter (如: AMD)", key="new_ticker_input", on_change=add_ticker)
    
    st.divider()
    st.subheader("管理板塊成份股")
    manage_sector = st.selectbox("選擇要管理的板塊", options=st.session_state.sector_data.keys())
    current_list = st.session_state.sector_data[manage_sector]
    updated_list = st.multiselect(
        f"移除 {manage_sector} 的股票",
        options=current_list,
        default=current_list,
        label_visibility="collapsed"
    )
    st.session_state.sector_data[manage_sector] = updated_list
    st.caption("Data Source: Yahoo Finance")

# ==========================================
# 4. 主畫面與策略
# ==========================================
st.title("Mark 美股智能戰情室")

if auto_refresh:
    st.info(f"系統運行中 - 每 {refresh_rate} 秒自動掃描全板塊")
elif manual_refresh:
    st.success("已手動觸發更新")
else:
    st.warning("系統已暫停")

def calculate_strategy(df):
    if df is None or len(df) < 90: return "-" 

    len_blue_h, len_blue_l = 24, 23
    len_yellow_h, len_yellow_l = 89, 90

    df['ema_blue_h'] = ta.ema(df['High'], length=len_blue_h)
    df['ema_blue_l'] = ta.ema(df['Low'], length=len_blue_l)
    df['ema_yellow_h'] = ta.ema(df['High'], length=len_yellow_h)
    df['ema_yellow_l'] = ta.ema(df['Low'], length=len_yellow_l)
    df['rsi'] = ta.rsi(df['Close'], length=14)
    df['vol_ma'] = ta.sma(df['Volume'], length=20)

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev5 = df.iloc[-6]

    vol_breakout = curr['Volume'] > (curr['vol_ma'] * 1.3)
    try:
        slope = abs(curr['ema_yellow_h'] - prev5['ema_yellow_h']) / prev5['ema_yellow_h'] * 1000
    except: slope = 0
    is_flat = slope < 0.2
    is_bear_trend = curr['ema_blue_h'] < curr['ema_yellow_l']
    
    crossover = (prev['Close'] < prev['ema_blue_h']) and (curr['Close'] > curr['ema_blue_h'])
    crossunder = (prev['Close'] > prev['ema_blue_l']) and (curr['Close'] < curr['ema_blue_l'])

    status = "-"
    if crossunder and is_bear_trend and vol_breakout and (curr['rsi'] > 30): status = "狙擊做空"
    elif crossover and vol_breakout: status = "強力買進"
    elif crossunder and (curr['rsi'] > 30): status = "賣出40%"
    elif crossover and not is_flat: status = "買進40%"
    elif crossover: status = "平空"
    elif crossunder: status = "破梯"
    return status

# ==========================================
# 5. 核心引擎：雲端專用優化版 (User-Agent + Chunking)
# ==========================================
@st.cache_data(ttl=5)
def fetch_all_raw_data(all_tickers):
    if not all_tickers:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    # 建立偽裝 Session (關鍵！騙過 Yahoo 認為我們是瀏覽器)
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })

    # 智能分批下載 (每次只抓 15 檔，太大量在雲端容易 Timeout 或被擋)
    def chunked_download(tickers, period, interval, retries=3):
        chunk_size = 15 
        all_dfs = []
        
        # 將股票清單切分成小塊
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i:i + chunk_size]
            
            # 重試機制
            for r in range(retries):
                try:
                    df = yf.download(
                        chunk, 
                        period=period, 
                        interval=interval, 
                        group_by='ticker', 
                        threads=True, 
                        progress=False,
                        auto_adjust=True,
                        session=session # 使用偽裝身份
                    )
                    if not df.empty:
                        all_dfs.append(df)
                        break # 成功就跳出重試
                    time.sleep(1) # 失敗等一下
                except Exception:
                    time.sleep(1)
            
            # 每抓完一批，休息 0.5 秒，避免觸發頻率限制
            time.sleep(0.5)

        # 合併所有數據
        if all_dfs:
            try:
                return pd.concat(all_dfs, axis=1)
            except:
                return pd.DataFrame()
        return pd.DataFrame()

    # 開始分批下載
    d5 = chunked_download(all_tickers, "1mo", "5m")
    d15 = chunked_download(all_tickers, "1mo", "15m")
    d1h = chunked_download(all_tickers, "6mo", "1h")
    d1d = chunked_download(all_tickers, "2y", "1d")

    return d5, d15, d1h, d1d

def process_sector_data(sector_tickers, d5, d15, d1h, d1d):
    results = []
    
    for ticker in sector_tickers:
        row = {"商品": ticker, "現價": "-", "10m":"-", "15m":"-", "30m":"-", "1h":"-", "2h":"-", "3h":"-", "4h":"-", "1d":"-"}
        try:
            def get_df(source_df):
                if source_df.empty: return pd.DataFrame()
                # 處理 MultiIndex
                if isinstance(source_df.columns, pd.MultiIndex):
                    if ticker in source_df.columns.levels[0]:
                        return source_df[ticker].dropna()
                # 處理 Single Index (極少見，但以防萬一)
                elif source_df.columns.nlevels == 1: 
                     # yfinance 單檔下載時沒有 ticker level，但我們用 chunked 下載通常不會發生
                     pass 
                return pd.DataFrame()

            df_5m = get_df(d5)
            df_15m = get_df(d15)
            df_1h = get_df(d1h)
            df_1d = get_df(d1d)

            if not df_5m.empty:
                row["現價"] = f"{df_5m['Close'].iloc[-1]:.2f}"
                df_10m = df_5m.resample("10T").agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'}).dropna()
                row["10m"] = calculate_strategy(df_10m)

            if not df_15m.empty:
                row["15m"] = calculate_strategy(df_15m)
                df_30m = df_15m.resample("30T").agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'}).dropna()
                row["30m"] = calculate_strategy(df_30m)

            if not df_1h.empty:
                row["1h"] = calculate_strategy(df_1h)
                df_2h = df_1h.resample("2h").agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'}).dropna()
                row["2h"] = calculate_strategy(df_2h)
                df_3h = df_1h.resample("3h").agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'}).dropna()
                row["3h"] = calculate_strategy(df_3h)
                df_4h = df_1h.resample("4h").agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'}).dropna()
                row["4h"] = calculate_strategy(df_4h)

            if not df_1d.empty:
                row["1d"] = calculate_strategy(df_1d)

        except Exception:
            pass
        results.append(row)
    
    return pd.DataFrame(results)

# ==========================================
# 6. 主畫面渲染流程
# ==========================================
main_placeholder = st.empty()

def color_map(val):
    s = str(val)
    if s == "強力買進": return 'background-color: #2962FF; color: white; font-weight: bold'
    if s == "買進40%": return 'background-color: #29B6F6; color: black; font-weight: bold'
    if s == "狙擊做空": return 'background-color: #D50000; color: white; font-weight: bold'
    if s == "賣出40%": return 'background-color: #FF5252; color: white; font-weight: bold'
    if s == "破梯": return 'background-color: #FF9800; color: black; font-weight: bold'
    if s == "平空": return 'background-color: #4CAF50; color: white; font-weight: bold'
    return ''

if auto_refresh or manual_refresh:
    with main_placeholder.container():
        
        all_unique_tickers = list(set([t for tickers in st.session_state.sector_data.values() for t in tickers]))
        
        raw_data_5m, raw_data_15m, raw_data_1h, raw_data_1d = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
        # 狀態欄顯示
        with st.status(f"正在雲端掃描 {len(all_unique_tickers)} 檔股票...", expanded=True) as status:
            if all_unique_tickers:
                raw_data_5m, raw_data_15m, raw_data_1h, raw_data_1d = fetch_all_raw_data(all_unique_tickers)
            status.update(label="雲端數據下載完成", state="complete", expanded=False)
        
        # 渲染表格
        for sector_name, tickers in st.session_state.sector_data.items():
            if not tickers: continue
            
            df_res = process_sector_data(tickers, raw_data_5m, raw_data_15m, raw_data_1h, raw_data_1d)
            
            st.subheader(f"{sector_name}")
            if not df_res.empty:
                cols_order = ["10m", "15m", "30m", "1h", "2h", "3h", "4h", "1d"]
                st.dataframe(
                    df_res.style.applymap(color_map, subset=cols_order),
                    height=(len(df_res) + 1) * 35 + 3,
                    use_container_width=True,
                    column_config={
                        "商品": st.column_config.TextColumn("商品", width="small"),
                        "現價": st.column_config.TextColumn("現價", width="small"),
                    }
                )
            else:
                st.warning(f"該板塊暫無數據 (Yahoo API 連線逾時)")

        st.caption(f"最後更新: {datetime.now().strftime('%H:%M:%S')}")

    if auto_refresh:
        time.sleep(refresh_rate)
        st.rerun()