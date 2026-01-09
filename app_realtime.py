"""
Mark 美股智能戰情室 - 即時監控版
使用 Flask + Polygon WebSocket + REST API
完全複刻 TradingView Pine Script 邏輯
"""

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import threading
import time
import json
import pytz

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# ==========================================
# 配置
# ==========================================
POLYGON_API_KEY = ""  # 在網頁上輸入

# 板塊配置（有序）
from collections import OrderedDict
SECTOR_DATA = OrderedDict([
    ("現有倉位", ["APLD", "CLSK"]),
    ("明星科技股", ["TSLA", "NVDA", "AAPL", "AMZN", "META", "NFLX", "ORCL", "PLTR", "MU", "AMD", "AVGO", "TSM", "QCOM", "ADBE", "DIS"]),
    ("英偉達持倉概念", ["NVDA", "APLD", "CRWV", "NBIS", "ARM", "WRD", "RXRX"]),
    ("核電", ["SMR", "OKLO", "UUUU", "NEE", "VST", "UEC", "NXE", "DJT", "LEU"]),
    ("量子計算", ["QBTS", "RGTI", "IONQ", "QUBT", "LAES"]),
    ("AI應用軟件", ["PLTR", "SOUN", "PATH", "TTD", "PINS", "ZETA", "TEM", "SHOP", "DOCU", "FIG", "RDDT", "SNOW", "MDB"]),
    ("特朗普概念", ["TSLA", "MARA", "DJT", "MSTR", "XOM", "CLSK", "RIOT", "COIN", "RUM", "UNH"]),
    ("智能駕駛", ["TSLA", "UBER"]),
    ("AI晶片", ["INTC", "NVDA", "TSM"]),
    ("加密貨幣", ["ASST", "SOFI", "BMNR", "BTBT", "BITF", "MARA", "MSTR", "IREN", "CLSK", "HOOD", "HIVE", "RIOT", "WULF", "CIFR", "GME", "COIN", "CRCL", "SBET", "GLXY", "HUT", "BTDR", "DJT"]),
    ("機器人概念", ["TSLA", "MBLY", "PATH", "RR", "SERV", "PDYN"]),
    ("無人機概念", ["ONDS", "ACHR", "JOBY", "RCAT", "KTOS", "UMAC", "AVAV"]),
    ("人工智慧", ["NVDA", "INTC", "SMCI", "NVTS", "AMD", "TSM", "AVGO", "QCOM"]),
    ("半導體概念", ["INTC", "NVDA", "MU", "AMD", "AVGO", "LRCX", "TSM", "AMAT", "SMCI", "NVTS"]),
    ("太空概念", ["RKLB", "ASTS", "SIDU", "RDW", "PL", "LUNR", "SATS", "VSAT", "DXYZ", "FJET"]),
    ("稀土", ["CRML", "UAMY", "UUUU", "MP", "USAR", "AREC", "NB", "EOSE"]),
    ("鋰礦電池", ["LAC", "QS", "LAR", "ENVX", "SGML", "ALAB"]),
    ("存儲概念", ["MU", "SNDK", "WDC", "STX"]),
    ("自定義清單", ["APLD", "CLSK"]),
])

# 全局狀態
realtime_prices = {}  # {ticker: price}
stock_signals = {}    # {ticker: {timeframe: signal}}

# ==========================================
# 技術指標計算（與 TradingView 完全一致）
# ==========================================
def calculate_ema(series, length):
    """計算 EMA（與 TradingView 一致）"""
    return series.ewm(span=length, adjust=False).mean()

def calculate_rsi(series, length=14):
    """計算 RSI（與 TradingView 一致）"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(span=length, adjust=False).mean()
    avg_loss = loss.ewm(span=length, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_sma(series, length):
    """計算 SMA"""
    return series.rolling(window=length).mean()

def calculate_strategy(df, timeframe_minutes=60):
    """
    計算多軍一號/空軍一號策略
    完全複刻 TradingView Pine Script 邏輯
    TradingView 只在 K 線收盤時確認信號
    """
    if df is None or len(df) < 90:
        return "-"
    
    # EMA 參數（與 Pine Script 一致）
    len_blue_h, len_blue_l = 24, 23
    len_yellow_h, len_yellow_l = 89, 90
    
    # 計算指標
    df = df.copy()
    df['ema_blue_h'] = calculate_ema(df['High'], len_blue_h)
    df['ema_blue_l'] = calculate_ema(df['Low'], len_blue_l)
    df['ema_yellow_h'] = calculate_ema(df['High'], len_yellow_h)
    df['ema_yellow_l'] = calculate_ema(df['Low'], len_yellow_l)
    df['rsi'] = calculate_rsi(df['Close'], 14)
    df['vol_ma'] = calculate_sma(df['Volume'], 20)
    
    # 檢查最後一根 K 線是否已收盤
    # TradingView 只在收盤時確認信號
    last_bar_time = df.index[-1]
    now_utc = datetime.utcnow()
    
    # 如果最後一根 K 線開始時間 + 週期 > 現在時間，說明還沒收盤
    # 使用倒數第 2 根作為「當前已收盤」的 K 線
    if hasattr(last_bar_time, 'tzinfo') and last_bar_time.tzinfo is not None:
        now_utc = pytz.utc.localize(now_utc).astimezone(last_bar_time.tzinfo)
    
    bar_end_time = last_bar_time + timedelta(minutes=timeframe_minutes)
    
    if now_utc < bar_end_time:
        # 最後一根還沒收盤，用倒數第 2 根
        curr = df.iloc[-2]
        prev = df.iloc[-3]
        prev5 = df.iloc[-7]
    else:
        # 最後一根已收盤
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev5 = df.iloc[-6]
    
    # 爆量判斷（提高門檻到 1.5x，減少邊界誤判）
    vol_breakout = curr['Volume'] > (curr['vol_ma'] * 1.5)
    
    # 斜率判斷（橫盤檢測）
    try:
        slope = abs(curr['ema_yellow_h'] - prev5['ema_yellow_h']) / prev5['ema_yellow_h'] * 1000
    except:
        slope = 0
    is_flat = slope < 0.2
    
    # 空頭趨勢判斷
    is_bear_trend = curr['ema_blue_h'] < curr['ema_yellow_l']
    
    # Crossover/Crossunder 判斷（與 Pine Script 完全一致）
    crossover = (prev['Close'] < prev['ema_blue_h']) and (curr['Close'] > curr['ema_blue_h'])
    crossunder = (prev['Close'] > prev['ema_blue_l']) and (curr['Close'] < curr['ema_blue_l'])
    
    # 策略判斷（只保留 4 個核心信號）
    status = "-"
    if crossunder and is_bear_trend and vol_breakout and (curr['rsi'] > 30):
        status = "狙擊做空"
    elif crossover and vol_breakout:
        status = "強力買進"
    elif crossunder and (curr['rsi'] > 30):
        status = "賣出40%"
    elif crossover and not is_flat:
        status = "買進40%"
    # 移除「平空」和「破梯」- 不再顯示
    # elif crossover:
    #     status = "平空"
    # elif crossunder:
    #     status = "破梯"
    
    return status

# ==========================================
# Polygon.io 數據獲取
# ==========================================
def fetch_polygon_bars(ticker, multiplier, timespan, days_back, api_key, filter_rth=True):
    """
    從 Polygon.io 獲取歷史 K 線
    filter_rth: 是否過濾只保留正常交易時段（日線不需要過濾）
    """
    if not api_key:
        return pd.DataFrame()
    
    now = datetime.utcnow()
    from_date = (now - timedelta(days=days_back)).strftime('%Y-%m-%d')
    to_date = now.strftime('%Y-%m-%d')
    
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": api_key
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("resultsCount", 0) > 0:
                results = data["results"]
                df = pd.DataFrame(results)
                df['timestamp'] = pd.to_datetime(df['t'], unit='ms')
                df = df.rename(columns={
                    'o': 'Open',
                    'h': 'High',
                    'l': 'Low',
                    'c': 'Close',
                    'v': 'Volume'
                })
                df = df.set_index('timestamp')
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
                
                # 只有分鐘/小時級別數據需要過濾 RTH
                if filter_rth and timespan in ['minute', 'hour']:
                    et_tz = pytz.timezone('America/New_York')
                    df.index = df.index.tz_localize('UTC').tz_convert(et_tz)
                    
                    df['hour'] = df.index.hour
                    df['minute'] = df.index.minute
                    df['time_decimal'] = df['hour'] + df['minute'] / 60.0
                    
                    # RTH: 9:30 (9.5) 到 16:00 (16.0)
                    df = df[(df['time_decimal'] >= 9.5) & (df['time_decimal'] < 16.0)]
                    df = df.drop(columns=['hour', 'minute', 'time_decimal'])
                
                return df
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
    
    return pd.DataFrame()

def fetch_realtime_price(ticker, api_key):
    """獲取即時股價"""
    if not api_key:
        return None
    
    # 方法 1: 使用 Previous Close API（最可靠）
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev"
    params = {"adjusted": "true", "apiKey": api_key}
    
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("results") and len(data["results"]) > 0:
                return data["results"][0]["c"]  # 收盤價
    except Exception as e:
        print(f"Price fetch error for {ticker}: {e}")
    
    # 方法 2: 備用 - 使用 Last Trade
    try:
        url2 = f"https://api.polygon.io/v2/last/trade/{ticker}"
        params2 = {"apiKey": api_key}
        response2 = requests.get(url2, params=params2, timeout=5)
        if response2.status_code == 200:
            data2 = response2.json()
            if data2.get("results"):
                return data2["results"]["p"]
    except:
        pass
    
    return None

def process_ticker(ticker, api_key):
    """處理單一股票的所有時間週期"""
    result = {
        "ticker": ticker,
        "price": "-",
        "10m": "-",
        "15m": "-",
        "30m": "-",
        "1h": "-",
        "2h": "-",
        "3h": "-",
        "4h": "-",
        "1d": "-"
    }
    
    try:
        # 獲取即時股價
        price = fetch_realtime_price(ticker, api_key)
        if price:
            result["price"] = f"{price:.2f}"
            realtime_prices[ticker] = price
        
        # 獲取 5分鐘數據（用於 10m resample）
        df_5m = fetch_polygon_bars(ticker, 5, 'minute', 7, api_key)
        if not df_5m.empty:
            df_10m = df_5m.resample("10min", label='right', closed='right').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
            result["10m"] = calculate_strategy(df_10m, timeframe_minutes=10)
        
        # 獲取 15分鐘數據
        df_15m = fetch_polygon_bars(ticker, 15, 'minute', 14, api_key)
        if not df_15m.empty:
            result["15m"] = calculate_strategy(df_15m, timeframe_minutes=15)
            df_30m = df_15m.resample("30min", label='right', closed='right').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
            result["30m"] = calculate_strategy(df_30m, timeframe_minutes=30)
        
        # 獲取 1小時數據
        df_1h = fetch_polygon_bars(ticker, 1, 'hour', 90, api_key)
        if not df_1h.empty:
            result["1h"] = calculate_strategy(df_1h, timeframe_minutes=60)
            df_2h = df_1h.resample("2h", label='right', closed='right').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
            result["2h"] = calculate_strategy(df_2h, timeframe_minutes=120)
            df_3h = df_1h.resample("3h", label='right', closed='right').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
            result["3h"] = calculate_strategy(df_3h, timeframe_minutes=180)
            df_4h = df_1h.resample("4h", label='right', closed='right').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
            result["4h"] = calculate_strategy(df_4h, timeframe_minutes=240)
        
        # 獲取日線數據（日線不需要 RTH 過濾）
        df_1d = fetch_polygon_bars(ticker, 1, 'day', 730, api_key, filter_rth=False)
        if not df_1d.empty:
            result["1d"] = calculate_strategy(df_1d, timeframe_minutes=1440)
        
    except Exception as e:
        print(f"Error processing {ticker}: {e}")
    
    return result

# ==========================================
# Flask 路由
# ==========================================
@app.route('/')
def index():
    return render_template('index.html', sectors=SECTOR_DATA)

@app.route('/api/scan', methods=['POST'])
def scan():
    """掃描所有股票"""
    from flask import request
    data = request.json
    api_key = data.get('api_key', '')
    
    if not api_key:
        return jsonify({"error": "API Key required"}), 400
    
    global POLYGON_API_KEY
    POLYGON_API_KEY = api_key
    
    results = {}
    all_tickers = list(set([t for tickers in SECTOR_DATA.values() for t in tickers]))
    
    # 並行處理（使用線程池）
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(process_ticker, ticker, api_key): ticker for ticker in all_tickers}
        for future in futures:
            try:
                result = future.result(timeout=30)
                results[result['ticker']] = result
            except Exception as e:
                print(f"Error: {e}")
    
    # 按板塊整理結果（保持順序）
    sector_results = []
    for sector_name, tickers in SECTOR_DATA.items():
        sector_results.append({
            "name": sector_name,
            "stocks": [results.get(t, {"ticker": t, "price": "-"}) for t in tickers]
        })
    
    return jsonify({
        "sectors": sector_results,
        "timestamp": datetime.now().strftime('%H:%M:%S')
    })

@app.route('/api/price/<ticker>')
def get_price(ticker):
    """獲取單一股票即時股價"""
    from flask import request
    api_key = request.args.get('api_key', POLYGON_API_KEY)
    price = fetch_realtime_price(ticker, api_key)
    return jsonify({"ticker": ticker, "price": price})

@app.route('/api/debug/<ticker>/<timeframe>')
def debug_ticker(ticker, timeframe):
    """調試特定股票的特定時間週期（查看詳細計算過程）"""
    from flask import request
    api_key = request.args.get('api_key', POLYGON_API_KEY)
    
    if not api_key:
        return jsonify({"error": "API Key required"}), 400
    
    # 根據 timeframe 獲取對應數據
    df = None
    tf_minutes = 60  # 默認值
    
    if timeframe == '10m':
        df_5m = fetch_polygon_bars(ticker, 5, 'minute', 7, api_key)
        tf_minutes = 10
        if not df_5m.empty:
            df = df_5m.resample("10min", label='right', closed='right').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
    elif timeframe == '15m':
        df = fetch_polygon_bars(ticker, 15, 'minute', 14, api_key)
        tf_minutes = 15
    elif timeframe == '30m':
        df_15m = fetch_polygon_bars(ticker, 15, 'minute', 14, api_key)
        tf_minutes = 30
        if not df_15m.empty:
            df = df_15m.resample("30min", label='right', closed='right').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
    elif timeframe == '1h':
        df = fetch_polygon_bars(ticker, 1, 'hour', 90, api_key)
        tf_minutes = 60
    elif timeframe == '2h':
        df_1h = fetch_polygon_bars(ticker, 1, 'hour', 90, api_key)
        tf_minutes = 120
        if not df_1h.empty:
            df = df_1h.resample("2h", label='right', closed='right').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
    elif timeframe == '3h':
        df_1h = fetch_polygon_bars(ticker, 1, 'hour', 90, api_key)
        tf_minutes = 180
        if not df_1h.empty:
            df = df_1h.resample("3h", label='right', closed='right').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
    elif timeframe == '4h':
        df_1h = fetch_polygon_bars(ticker, 1, 'hour', 90, api_key)
        tf_minutes = 240
        if not df_1h.empty:
            df = df_1h.resample("4h", label='right', closed='right').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
    elif timeframe == '1d':
        df = fetch_polygon_bars(ticker, 1, 'day', 730, api_key, filter_rth=False)
        tf_minutes = 1440
    
    if df is None or df.empty or len(df) < 90:
        return jsonify({"error": f"Insufficient data for {ticker} {timeframe}", "data_count": len(df) if df is not None else 0})
    
    # 計算指標
    df_calc = df.copy()
    df_calc['ema_blue_h'] = calculate_ema(df_calc['High'], 24)
    df_calc['ema_blue_l'] = calculate_ema(df_calc['Low'], 23)
    df_calc['ema_yellow_h'] = calculate_ema(df_calc['High'], 89)
    df_calc['ema_yellow_l'] = calculate_ema(df_calc['Low'], 90)
    df_calc['rsi'] = calculate_rsi(df_calc['Close'], 14)
    df_calc['vol_ma'] = calculate_sma(df_calc['Volume'], 20)
    
    # 檢查最後一根是否已收盤（與 calculate_strategy 邏輯一致）
    last_bar_time = df_calc.index[-1]
    now_utc = datetime.utcnow()
    if hasattr(last_bar_time, 'tzinfo') and last_bar_time.tzinfo is not None:
        now_utc = pytz.utc.localize(now_utc).astimezone(last_bar_time.tzinfo)
    bar_end_time = last_bar_time + timedelta(minutes=tf_minutes)
    bar_is_closed = now_utc >= bar_end_time
    
    if bar_is_closed:
        curr = df_calc.iloc[-1]
        prev = df_calc.iloc[-2]
        prev5 = df_calc.iloc[-6]
    else:
        curr = df_calc.iloc[-2]
        prev = df_calc.iloc[-3]
        prev5 = df_calc.iloc[-7]
    
    vol_breakout = curr['Volume'] > (curr['vol_ma'] * 1.5)
    try:
        slope = abs(curr['ema_yellow_h'] - prev5['ema_yellow_h']) / prev5['ema_yellow_h'] * 1000
    except:
        slope = 0
    is_flat = slope < 0.2
    is_bear_trend = curr['ema_blue_h'] < curr['ema_yellow_l']
    
    crossover = (prev['Close'] < prev['ema_blue_h']) and (curr['Close'] > curr['ema_blue_h'])
    crossunder = (prev['Close'] > prev['ema_blue_l']) and (curr['Close'] < curr['ema_blue_l'])
    
    signal = calculate_strategy(df, timeframe_minutes=tf_minutes)
    
    # 返回最後5根 K 線和計算細節
    last_bars = []
    for i in range(-5, 0):
        bar = df_calc.iloc[i]
        last_bars.append({
            "index": i,
            "time": str(bar.name),
            "Open": round(bar['Open'], 2),
            "High": round(bar['High'], 2),
            "Low": round(bar['Low'], 2),
            "Close": round(bar['Close'], 2),
            "Volume": int(bar['Volume']),
            "ema_blue_h": round(bar['ema_blue_h'], 2),
            "ema_blue_l": round(bar['ema_blue_l'], 2),
            "rsi": round(bar['rsi'], 2) if not pd.isna(bar['rsi']) else None
        })
    
    return jsonify({
        "ticker": ticker,
        "timeframe": timeframe,
        "data_count": len(df),
        "bar_is_closed": bar_is_closed,
        "using_bar": "最後一根 (已收盤)" if bar_is_closed else "倒數第二根 (最後一根未收盤)",
        "last_bars": last_bars,
        "calculation": {
            "curr_close": float(round(curr['Close'], 2)),
            "prev_close": float(round(prev['Close'], 2)),
            "curr_ema_blue_h": float(round(curr['ema_blue_h'], 2)),
            "prev_ema_blue_h": float(round(prev['ema_blue_h'], 2)),
            "curr_ema_blue_l": float(round(curr['ema_blue_l'], 2)),
            "prev_ema_blue_l": float(round(prev['ema_blue_l'], 2)),
            "curr_volume": int(curr['Volume']),
            "vol_ma": int(curr['vol_ma']),
            "vol_ratio": float(round(curr['Volume'] / curr['vol_ma'], 2)) if curr['vol_ma'] > 0 else 0,
            "rsi": float(round(curr['rsi'], 2)) if not pd.isna(curr['rsi']) else None,
            "slope": float(round(slope, 4)),
            "is_flat": bool(is_flat),
            "is_bear_trend": bool(is_bear_trend),
            "vol_breakout": bool(vol_breakout),
            "crossover": bool(crossover),
            "crossunder": bool(crossunder),
            "crossover_check": f"prev_close({round(prev['Close'], 2)}) < prev_ema_blue_h({round(prev['ema_blue_h'], 2)}) = {bool(prev['Close'] < prev['ema_blue_h'])} AND curr_close({round(curr['Close'], 2)}) > curr_ema_blue_h({round(curr['ema_blue_h'], 2)}) = {bool(curr['Close'] > curr['ema_blue_h'])}",
            "crossunder_check": f"prev_close({round(prev['Close'], 2)}) > prev_ema_blue_l({round(prev['ema_blue_l'], 2)}) = {bool(prev['Close'] > prev['ema_blue_l'])} AND curr_close({round(curr['Close'], 2)}) < curr_ema_blue_l({round(curr['ema_blue_l'], 2)}) = {bool(curr['Close'] < curr['ema_blue_l'])}"
        },
        "signal": signal
    })

# ==========================================
# 啟動
# ==========================================
if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5001)

