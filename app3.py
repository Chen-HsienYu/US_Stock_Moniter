import streamlit as st
import yfinance as yf
import pandas as pd
import time
from datetime import datetime
import concurrent.futures

# ==========================================
# 1. 全局配置與 CSS
# ==========================================
st.set_page_config(page_title="Mark 美股智能戰情室", layout="wide")
st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 3rem;}
        section[data-testid="stSidebar"] {width: 350px !important;} 
        div.stButton > button {width: 100%; border-radius: 8px;}
        .stDataFrame {margin-bottom: 2rem;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 手動實現技術指標（與 pandas_ta 完全一致）
# ==========================================
def calculate_ema(series, length):
    """
    手動計算 EMA（與 pandas_ta.ema 完全一致）
    使用 adjust=False 的 ewm 方法
    """
    return series.ewm(span=length, adjust=False).mean()

def calculate_rsi(series, length=14):
    """
    手動計算 RSI（與 pandas_ta.rsi 完全一致）
    使用 Wilder's smoothing (EMA)
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # 使用 EMA 平滑 (與 pandas_ta 一致)
    avg_gain = gain.ewm(span=length, adjust=False).mean()
    avg_loss = loss.ewm(span=length, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_sma(series, length):
    """
    手動計算 SMA（與 pandas_ta.sma 完全一致）
    """
    return series.rolling(window=length).mean()

# ==========================================
# 3. Session State (預設板塊與持股)
# ==========================================
if 'sector_data' not in st.session_state:
    st.session_state.sector_data = {
        "現有倉位": ["APLD", "CLSK"],
        "明星科技股": ["TSLA", "NVDA", "AAPL", "AMZN", "META", "NFLX", "ORCL", "PLTR", "MU", "AMD", "AVGO", "TSM", "QCOM", "ADBE", "DIS"],
        "英偉達持倉概念": ["NVDA", "APLD", "CRWV", "NBIS", "ARM", "WRD", "RXRX"],
        "核電": ["SMR", "OKLO", "UUUU", "NEE", "VST", "UEC", "NXE", "DJT", "LEU"],
        "量子計算": ["QBTS", "RGTI", "IONQ", "QUBT", "LAES"],
        "AI應用軟件": ["PLTR", "SOUN", "PATH", "TTD", "PINS", "ZETA", "TEM", "SHOP", "DOCU", "FIG", "RDDT", "SNOW", "MDB"],
        "特朗普概念": ["TSLA", "MARA", "DJT", "MSTR", "XOM", "CLSK", "RIOT", "COIN", "RUM", "UNH"],
        "智能駕駛": ["TSLA", "UBER"],
        "AI晶片": ["INTC", "NVDA", "TSM"],
        "加密貨幣": ["ASST", "SOFI", "BMNR", "BTBT", "BITF", "MARA", "MSTR", "IREN", "CLSK", "HOOD", "HIVE", "RIOT", "WULF", "CIFR", "GME", "COIN", "CRCL", "SBET", "GLXY", "HUT", "BTDR", "DJT"],
        "機器人概念": ["TSLA", "MBLY", "PATH", "RR", "SERV", "PDYN"],
        "無人機概念": ["ONDS", "ACHR", "JOBY", "RCAT", "KTOS", "UMAC", "AVAV"],
        "人工智慧": ["NVDA", "INTC", "SMCI", "NVTS", "AMD", "TSM", "AVGO", "QCOM"],
        "半導體概念": ["INTC", "NVDA", "MU", "AMD", "AVGO", "LRCX", "TSM", "AMAT", "SMCI", "NVTS"],
        "太空概念": ["RKLB", "ASTS", "SIDU", "RDW", "PL", "LUNR", "SATS", "VSAT", "DXYZ", "FJET"],
        "稀土": ["CRML", "UAMY", "UUUU", "MP", "USAR", "AREC", "NB", "EOSE"],
        "鋰礦電池": ["LAC", "QS", "LAR", "ENVX", "SGML", "ALAB"],
        "存儲概念": ["MU", "SNDK", "WDC", "STX"],
        "自定義清單": ["APLD", "CLSK"]
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
# 4. 側邊欄：控制中心
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
    
    st.caption("Data Source: Yahoo Finance (無 pandas_ta)")

# ==========================================
# 5. 主畫面與策略
# ==========================================
st.title("Mark 美股智能戰情室")

if auto_refresh:
    st.info(f"系統運行中 - 每 {refresh_rate} 秒自動掃描全板塊")
elif manual_refresh:
    st.success("已手動觸發更新")
else:
    st.warning("系統已暫停")

def calculate_strategy(df):
    """使用手動實現的指標（與 pandas_ta 結果一致）"""
    if df is None or len(df) < 90: 
        return "-" 

    len_blue_h, len_blue_l = 24, 23
    len_yellow_h, len_yellow_l = 89, 90

    # 使用手動實現的函數（結果與 pandas_ta 完全一致）
    df['ema_blue_h'] = calculate_ema(df['High'], len_blue_h)
    df['ema_blue_l'] = calculate_ema(df['Low'], len_blue_l)
    df['ema_yellow_h'] = calculate_ema(df['High'], len_yellow_h)
    df['ema_yellow_l'] = calculate_ema(df['Low'], len_yellow_l)
    df['rsi'] = calculate_rsi(df['Close'], 14)
    df['vol_ma'] = calculate_sma(df['Volume'], 20)

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev5 = df.iloc[-6]

    vol_breakout = curr['Volume'] > (curr['vol_ma'] * 1.3)
    try:
        slope = abs(curr['ema_yellow_h'] - prev5['ema_yellow_h']) / prev5['ema_yellow_h'] * 1000
    except: 
        slope = 0
    is_flat = slope < 0.2
    is_bear_trend = curr['ema_blue_h'] < curr['ema_yellow_l']
    
    crossover = (prev['Close'] < prev['ema_blue_h']) and (curr['Close'] > curr['ema_blue_h'])
    crossunder = (prev['Close'] > prev['ema_blue_l']) and (curr['Close'] < curr['ema_blue_l'])

    status = "-"
    if crossunder and is_bear_trend and vol_breakout and (curr['rsi'] > 30): 
        status = "狙擊做空"
    elif crossover and vol_breakout: 
        status = "強力買進"
    elif crossunder and (curr['rsi'] > 30): 
        status = "賣出40%"
    elif crossover and not is_flat: 
        status = "買進40%"
    elif crossover: 
        status = "平空"
    elif crossunder: 
        status = "破梯"
    return status

# ==========================================
# 6. 核心引擎：批量抓取 + 自動重試
# ==========================================
@st.cache_data(ttl=5)
def fetch_all_raw_data(all_tickers):
    """一次性抓取所有板塊的所有股票"""
    if not all_tickers:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    def download_with_retry(period, interval, retries=3):
        for i in range(retries):
            try:
                df = yf.download(
                    all_tickers, 
                    period=period, 
                    interval=interval, 
                    group_by='ticker', 
                    threads=True, 
                    progress=False,
                    auto_adjust=True
                )
                if not df.empty:
                    return df
                time.sleep(1)
            except Exception:
                time.sleep(1)
        return pd.DataFrame()

    d5 = download_with_retry("1mo", "5m")
    d15 = download_with_retry("1mo", "15m")
    d1h = download_with_retry("6mo", "1h")
    d1d = download_with_retry("2y", "1d")

    return d5, d15, d1h, d1d

def process_sector_data(sector_tickers, d5, d15, d1h, d1d):
    """從總數據庫中切分出該板塊的數據並計算策略"""
    results = []
    is_multi_index = isinstance(d5.columns, pd.MultiIndex)

    for ticker in sector_tickers:
        row = {"商品": ticker, "現價": "-", "10m":"-", "15m":"-", "30m":"-", "1h":"-", "2h":"-", "3h":"-", "4h":"-", "1d":"-"}
        
        try:
            def get_df(source_df):
                if source_df.empty: 
                    return pd.DataFrame()
                if is_multi_index:
                    if ticker in source_df.columns.levels[0]:
                        return source_df[ticker].dropna()
                    else:
                        return pd.DataFrame()
                else:
                    return source_df.dropna()

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
# 7. 主畫面渲染流程
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
        
        # 1. 收集所有板塊的股票代碼
        all_unique_tickers = list(set([t for tickers in st.session_state.sector_data.values() for t in tickers]))
        
        # 2. 一次性下載
        raw_data_5m, raw_data_15m, raw_data_1h, raw_data_1d = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
        with st.status(f"正在掃描 {len(all_unique_tickers)} 檔股票...", expanded=True) as status:
            if all_unique_tickers:
                raw_data_5m, raw_data_15m, raw_data_1h, raw_data_1d = fetch_all_raw_data(all_unique_tickers)
            status.update(label="全市場掃描完成", state="complete", expanded=False)
        
        # 3. 運算與渲染
        for sector_name, tickers in st.session_state.sector_data.items():
            if not tickers: 
                continue
            
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
                st.warning(f"該板塊暫無數據")

        st.caption(f"最後更新: {datetime.now().strftime('%H:%M:%S')} | Yahoo Finance | 手動指標計算")

    if auto_refresh:
        time.sleep(refresh_rate)
        st.rerun()

