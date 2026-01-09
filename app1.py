import streamlit as st
import pandas as pd
import pandas_ta as ta
import time
import requests
from datetime import datetime, timedelta
import pytz

# ==========================================
# 1. 全局配置與 CSS
# ==========================================
st.set_page_config(page_title="Mark 美股智能戰情室 Pro", layout="wide")

st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 3rem;}
        section[data-testid="stSidebar"] {width: 350px !important;} 
        div.stButton > button {width: 100%; border-radius: 8px;}
        .stDataFrame {margin-bottom: 2rem;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. Session State (預設板塊與持股)
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
# 3. 側邊欄：控制中心
# ==========================================
with st.sidebar:
    st.header("🛡️ Mark 戰情室 Pro")
    st.caption("⚡ Polygon.io 即時監控 | 與 TradingView 同步")
    
    # Polygon API Key
    if 'polygon_api_key' not in st.session_state:
        st.session_state.polygon_api_key = ""
    
    api_key = st.text_input("Polygon.io API Key", 
                           value=st.session_state.polygon_api_key,
                           type="password",
                           help="輸入你的 Polygon.io API Key")
    if api_key:
        st.session_state.polygon_api_key = api_key
        st.success("✅ API Key 已設定")
    else:
        st.error("⚠️ 請輸入 API Key")
    
    st.divider()
    
    st.subheader("系統狀態")
    auto_refresh = st.toggle("啟動自動刷新", value=False)
    manual_refresh = st.button("🔄 立即手動刷新", type="primary")
    with st.expander("設定刷新頻率"):
        refresh_rate = st.slider("秒數", 10, 300, 30)  # 改成30秒，減少請求
    
    st.divider()
    
    # 調試開關
    st.session_state.debug_mode = st.checkbox("🔍 顯示信號詳情", value=True)
    st.session_state.debug_ticker = st.text_input("調試股票代碼", value="TSLA")
    
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
    
    st.caption("Data: Yahoo Finance (TradingView 驗證)")

# ==========================================
# 4. 主畫面與策略 (使用已驗證的邏輯)
# ==========================================
st.title("Mark 美股智能戰情室")

if auto_refresh:
    st.info(f"系統運行中 - 每 {refresh_rate} 秒自動掃描全板塊")
elif manual_refresh:
    st.success("已手動觸發更新")
else:
    st.warning("系統已暫停")

def calculate_strategy(df, ticker=None, timeframe=None, debug=False):
    """使用與 TradingView 一致的策略邏輯"""
    if df is None or len(df) < 90: 
        return "-" 

    len_blue_h, len_blue_l = 24, 23
    len_yellow_h, len_yellow_l = 89, 90

    df['ema_blue_h'] = ta.ema(df['High'], length=len_blue_h)
    df['ema_blue_l'] = ta.ema(df['Low'], length=len_blue_l)
    df['ema_yellow_h'] = ta.ema(df['High'], length=len_yellow_h)
    df['ema_yellow_l'] = ta.ema(df['Low'], length=len_yellow_l)
    df['rsi'] = ta.rsi(df['Close'], length=14)
    df['vol_ma'] = ta.sma(df['Volume'], length=20)

    # 使用最後一根作為「當前」（與 TradingView 邏輯一致）
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

    # 調試輸出（任何有信號都顯示，不只是 crossover）
    if debug and ticker and (crossover or crossunder):
        st.sidebar.write(f"### 📊 {ticker} - {timeframe}")
        st.sidebar.write(f"**信號類型: {'🟢 Crossover' if crossover else '🔴 Crossunder'}**")
        st.sidebar.write("")
        
        # 顯示最後 3 根 K 線（標註哪根是當前判斷用的）
        st.sidebar.write(f"**最後 3 根 K 線時間與成交量:**")
        for i in range(-3, 0):
            k = df.iloc[i]
            marker = " ← 當前判斷 (即時)" if i == -1 else (" ← 前一根" if i == -2 else "")
            st.sidebar.write(f"  {i}: {k.name.strftime('%m-%d %H:%M')} | Vol: {k['Volume']:,.0f}{marker}")
        st.sidebar.write("")
        
        if crossover:
            st.sidebar.write(f"**價格突破藍梯上沿:**")
            st.sidebar.write(f"  - 前一根收盤: ${prev['Close']:.2f} ({prev.name.strftime('%H:%M')})")
            st.sidebar.write(f"  - 前一根藍梯上: ${prev['ema_blue_h']:.2f}")
            st.sidebar.write(f"  - 當前收盤: ${curr['Close']:.2f} ({curr.name.strftime('%H:%M')})")
            st.sidebar.write(f"  - 當前藍梯上: ${curr['ema_blue_h']:.2f}")
            st.sidebar.write(f"  - ✅ 穿越確認: {prev['Close']:.2f} < {prev['ema_blue_h']:.2f} → {curr['Close']:.2f} > {curr['ema_blue_h']:.2f}")
        else:
            st.sidebar.write(f"**價格跌破藍梯下沿:**")
            st.sidebar.write(f"  - 前一根收盤: ${prev['Close']:.2f} ({prev.name.strftime('%H:%M')})")
            st.sidebar.write(f"  - 前一根藍梯下: ${prev['ema_blue_l']:.2f}")
            st.sidebar.write(f"  - 當前收盤: ${curr['Close']:.2f} ({curr.name.strftime('%H:%M')})")
            st.sidebar.write(f"  - 當前藍梯下: ${curr['ema_blue_l']:.2f}")
            st.sidebar.write(f"  - ✅ 跌破確認: {prev['Close']:.2f} > {prev['ema_blue_l']:.2f} → {curr['Close']:.2f} < {curr['ema_blue_l']:.2f}")
            st.sidebar.write(f"  - RSI: {curr['rsi']:.2f}")
        
        st.sidebar.write(f"")
        st.sidebar.write(f"**成交量檢測:**")
        st.sidebar.write(f"  - 當前成交量: {curr['Volume']:,.0f}")
        st.sidebar.write(f"  - 20日均量: {curr['vol_ma']:,.0f}")
        st.sidebar.write(f"  - 爆量倍數: {curr['Volume'] / curr['vol_ma']:.2f}x")
        st.sidebar.write(f"  - 需要: 1.30x")
        st.sidebar.write(f"  - **爆量狀態: {'✅ 是' if vol_breakout else '❌ 否'}**")
        st.sidebar.write(f"")
        st.sidebar.write(f"**橫盤檢測:**")
        st.sidebar.write(f"  - 斜率: {slope:.4f}")
        st.sidebar.write(f"  - 橫盤狀態: {'是' if is_flat else '否'}")
        st.sidebar.write(f"")
        st.sidebar.write(f"**最終信號: {status}**")
        st.sidebar.divider()

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
# 5. 核心引擎：Polygon.io 數據獲取
# ==========================================
def fetch_polygon_bars(ticker, multiplier, timespan, from_date, to_date, api_key):
    """
    從 Polygon.io 獲取歷史 K 線數據
    timespan: minute, hour, day
    multiplier: 5 (for 5min), 15 (for 15min), 1 (for 1hour), etc.
    """
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": api_key
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("resultsCount", 0) > 0:
                results = data["results"]
                df = pd.DataFrame(results)
                # 轉換 Polygon 格式到標準 OHLCV
                df['timestamp'] = pd.to_datetime(df['t'], unit='ms', utc=True)
                # 轉換到美東時間（與 TradingView 一致）
                et_tz = pytz.timezone('America/New_York')
                df['timestamp'] = df['timestamp'].dt.tz_convert(et_tz)
                df = df.rename(columns={
                    'o': 'Open',
                    'h': 'High',
                    'l': 'Low',
                    'c': 'Close',
                    'v': 'Volume'
                })
                df = df.set_index('timestamp')
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
                return df
    except Exception as e:
        if st.session_state.get('debug_mode'):
            st.sidebar.error(f"Polygon Error ({ticker}): {e}")
    
    return pd.DataFrame()

@st.cache_data(ttl=10)  # 10秒快取，確保即時性
def fetch_all_raw_data(all_tickers, api_key):
    """使用 Polygon.io 獲取所有股票數據（包含當前未收盤K線）"""
    if not all_tickers or not api_key:
        return {}, {}, {}, {}
    
    # 計算日期範圍（使用 UTC 時間，Polygon 會自動處理時區）
    now_utc = datetime.utcnow()
    
    # 5分鐘數據：最近7天（確保足夠數據計算指標）
    from_5m = (now_utc - timedelta(days=7)).strftime('%Y-%m-%d')
    # 15分鐘數據：最近14天
    from_15m = (now_utc - timedelta(days=14)).strftime('%Y-%m-%d')
    # 1小時數據：最近90天
    from_1h = (now_utc - timedelta(days=90)).strftime('%Y-%m-%d')
    # 1天數據：最近730天（2年，計算長期指標）
    from_1d = (now_utc - timedelta(days=730)).strftime('%Y-%m-%d')
    to_date = now_utc.strftime('%Y-%m-%d')
    
    # 儲存數據（用字典代替 MultiIndex DataFrame）
    data_5m = {}
    data_15m = {}
    data_1h = {}
    data_1d = {}
    
    # 並行抓取所有股票
    import concurrent.futures
    
    def fetch_ticker_all_timeframes(ticker):
        return {
            'ticker': ticker,
            '5m': fetch_polygon_bars(ticker, 5, 'minute', from_5m, to_date, api_key),
            '15m': fetch_polygon_bars(ticker, 15, 'minute', from_15m, to_date, api_key),
            '1h': fetch_polygon_bars(ticker, 1, 'hour', from_1h, to_date, api_key),
            '1d': fetch_polygon_bars(ticker, 1, 'day', from_1d, to_date, api_key)
        }
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_ticker_all_timeframes, all_tickers))
    
    for result in results:
        ticker = result['ticker']
        data_5m[ticker] = result['5m']
        data_15m[ticker] = result['15m']
        data_1h[ticker] = result['1h']
        data_1d[ticker] = result['1d']
    
    return data_5m, data_15m, data_1h, data_1d

def process_sector_data(sector_tickers, d5, d15, d1h, d1d, debug_mode=False, debug_ticker=""):
    """處理 Polygon.io 數據（字典格式）"""
    results = []

    for ticker in sector_tickers:
        row = {"商品": ticker, "現價": "-", "10m":"-", "15m":"-", "30m":"-", "1h":"-", "2h":"-", "3h":"-", "4h":"-", "1d":"-"}
        
        # 判斷是否為調試目標
        is_debug = debug_mode and (ticker == debug_ticker.upper())
        
        try:
            # 從字典中獲取該股票的數據
            df_5m = d5.get(ticker, pd.DataFrame())
            df_15m = d15.get(ticker, pd.DataFrame())
            df_1h = d1h.get(ticker, pd.DataFrame())
            df_1d = d1d.get(ticker, pd.DataFrame())

            if not df_5m.empty:
                # 顯示最新價格（當前K線收盤價）
                latest_price = df_5m['Close'].iloc[-1]
                row["現價"] = f"{latest_price:.2f}"
                # Resample 到 10分鐘（會包含當前未收盤的K線）
                df_10m = df_5m.resample("10min").agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'}).dropna()
                row["10m"] = calculate_strategy(df_10m, ticker, "10m", is_debug)

            if not df_15m.empty:
                row["15m"] = calculate_strategy(df_15m, ticker, "15m", is_debug)
                df_30m = df_15m.resample("30min").agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'}).dropna()
                row["30m"] = calculate_strategy(df_30m, ticker, "30m", is_debug)

            if not df_1h.empty:
                row["1h"] = calculate_strategy(df_1h, ticker, "1h", is_debug)
                df_2h = df_1h.resample("2h").agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'}).dropna()
                row["2h"] = calculate_strategy(df_2h, ticker, "2h", is_debug)
                df_3h = df_1h.resample("3h").agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'}).dropna()
                row["3h"] = calculate_strategy(df_3h, ticker, "3h", is_debug)
                df_4h = df_1h.resample("4h").agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'}).dropna()
                row["4h"] = calculate_strategy(df_4h, ticker, "4h", is_debug)

            if not df_1d.empty:
                row["1d"] = calculate_strategy(df_1d, ticker, "1d", is_debug)

        except Exception as e:
            if is_debug:
                st.sidebar.error(f"處理 {ticker} 時出錯: {e}")
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
    # 檢查 API Key
    if not st.session_state.get('polygon_api_key'):
        st.error("⚠️ 請先在側邊欄輸入 Polygon.io API Key")
        st.stop()
    
    with main_placeholder.container():
        
        # 1. 收集所有板塊的股票代碼
        all_unique_tickers = list(set([t for tickers in st.session_state.sector_data.values() for t in tickers]))
        
        # 2. 從 Polygon.io 獲取數據
        raw_data_5m, raw_data_15m, raw_data_1h, raw_data_1d = {}, {}, {}, {}
        
        with st.status(f"🔄 正在從 Polygon.io 掃描 {len(all_unique_tickers)} 檔股票...", expanded=True) as status:
            if all_unique_tickers:
                raw_data_5m, raw_data_15m, raw_data_1h, raw_data_1d = fetch_all_raw_data(
                    all_unique_tickers, 
                    st.session_state.polygon_api_key
                )
            status.update(label="✅ Polygon.io 數據獲取完成", state="complete", expanded=False)
        
        # 3. 運算與渲染
        for sector_name, tickers in st.session_state.sector_data.items():
            if not tickers: 
                continue
            
            # 傳遞調試參數
            df_res = process_sector_data(
                tickers, raw_data_5m, raw_data_15m, raw_data_1h, raw_data_1d,
                debug_mode=st.session_state.get('debug_mode', False),
                debug_ticker=st.session_state.get('debug_ticker', '')
            )
            
            st.subheader(f"📊 {sector_name}")
            if not df_res.empty:
                cols_order = ["10m", "15m", "30m", "1h", "2h", "3h", "4h", "1d"]
                st.dataframe(
                    df_res.style.map(color_map, subset=cols_order),
                    height=(len(df_res) + 1) * 35 + 3,
                    use_container_width=True,
                    column_config={
                        "商品": st.column_config.TextColumn("商品", width="small"),
                        "現價": st.column_config.TextColumn("現價", width="small"),
                    }
                )
            else:
                st.warning(f"該板塊暫無數據")

        st.caption(f"✅ 最後更新: {datetime.now().strftime('%H:%M:%S')} | Polygon.io 即時數據 | 已驗證與 TradingView 同步")

    if auto_refresh:
        time.sleep(refresh_rate)
        st.rerun()
