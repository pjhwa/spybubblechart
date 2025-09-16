import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime, timedelta
import requests
from io import StringIO
from tqdm import tqdm
import time
import pickle
import os
import logging
import argparse
import bisect  # closest date 매핑을 위한 bisect

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sp500_log.txt", mode='a'),
        logging.StreamHandler()
    ]
)

def get_sp500_tickers():
    logging.info("Starting to get S&P 500 tickers...")
    cache_file = 'sp500_tickers.pkl'
    if os.path.exists(cache_file):
        logging.info(f"Loading tickers from cache: {cache_file}")
        with open(cache_file, 'rb') as f:
            return pickle.load(f)
    
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    table = pd.read_html(StringIO(response.text))[0]
    df = pd.DataFrame({'Ticker': table['Symbol'], 'Sector': table['GICS Sector']})
    
    with open(cache_file, 'wb') as f:
        pickle.dump(df, f)
    logging.info("Tickers loaded and cached.")
    return df

def download_data(tickers, start_date, end_date, interval='1d', chunksize=20):
    logging.info(f"Downloading price data for period {start_date} to {end_date} with interval {interval}")
    original_end_date = end_date  # 원래 end_date 저장
    cache_file = f'price_data_{start_date}_{original_end_date}_{interval}.pkl'
    if os.path.exists(cache_file):
        logging.info(f"Loading price data from cache: {cache_file} (skipping download as cache exists for identical options)")
        with open(cache_file, 'rb') as f:
            data = pickle.load(f)
        return data
    
    max_attempts = 5  # 최대 5회 시도 (비거래일 조정)
    attempts = 0
    data = pd.DataFrame()
    
    while data.empty and attempts < max_attempts:
        attempts += 1
        current_date = datetime.now().strftime('%Y-%m-%d')
        end_date = min(end_date, current_date)
        
        new_start = data.index.max().strftime('%Y-%m-%d') if not data.empty else start_date
        if new_start >= end_date:
            break
        
        new_data_frames = []
        for i in tqdm(range(0, len(tickers), chunksize), desc="Downloading new price data"):
            chunk = tickers[i:i+chunksize]
            logging.info(f"Processing chunk {i//chunksize + 1}/{len(tickers)//chunksize + 1}: {chunk}")
            success = False
            retries = 0
            max_retries = 3
            while not success and retries < max_retries:
                try:
                    chunk_data = yf.download(chunk, start=new_start, end=end_date, interval=interval, progress=True, threads=False, auto_adjust=False)['Adj Close']
                    new_data_frames.append(chunk_data)
                    success = True
                except Exception as e:
                    logging.error(f"Error in chunk {i//chunksize + 1} (retry {retries+1}/{max_retries}): {e}")
                    retries += 1
                    time.sleep(5 * retries)
            if not success:
                logging.warning(f"Failed to download chunk {i//chunksize + 1} after {max_retries} retries. Skipping...")
            time.sleep(5)
        
        new_data = pd.concat(new_data_frames, axis=1).ffill().bfill()
        data = pd.concat([data, new_data]).drop_duplicates()
        
        if data.empty:
            logging.warning(f"No data for end_date {end_date}. Finding nearest trading day using SPY ticker.")
            # 개선: 'SPY' 티커로 최근 10일 데이터 다운로드하여 가장 최근 거래일 찾음
            try:
                spy_data = yf.download('SPY', start=(datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=10)).strftime('%Y-%m-%d'), end=end_date, interval=interval)['Adj Close']
                if not spy_data.empty:
                    nearest_trading_day = spy_data.index.max().strftime('%Y-%m-%d')
                    logging.info(f"Adjusting end_date to nearest trading day: {nearest_trading_day}")
                    end_date = nearest_trading_day
                else:
                    end_date = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
            except Exception as e:
                logging.error(f"Error finding trading day: {e}")
                end_date = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    
    if data.empty:
        logging.error("No valid data downloaded after adjustments. Exiting.")
        raise ValueError("No valid data downloaded after adjustments.")
    
    data.index.name = 'Date'
    with open(cache_file, 'wb') as f:
        pickle.dump(data, f)
    logging.info(f"Price data updated and cached for adjusted period (end_date: {end_date}).")
    return data

def get_market_caps(tickers):
    logging.info("Starting to get market caps...")
    cache_file = 'market_caps.pkl'
    if os.path.exists(cache_file):
        logging.info(f"Loading market caps from cache: {cache_file}")
        with open(cache_file, 'rb') as f:
            return pickle.load(f)
    
    market_caps = {}
    for ticker in tqdm(tickers, desc="Downloading market caps"):
        try:
            market_caps[ticker] = yf.Ticker(ticker).info.get('marketCap', np.nan)
        except Exception as e:
            logging.warning(f"Failed to get market cap for {ticker}: {e}")
            market_caps[ticker] = np.nan
    
    with open(cache_file, 'wb') as f:
        pickle.dump(market_caps, f)
    logging.info("Market caps loaded and cached.")
    return market_caps

sector_colors = {
    'Energy': 'blue', 'Health Care': 'green', 'Information Technology': 'red',
    'Financials': 'orange', 'Communication Services': 'purple', 'Utilities': 'yellow',
    'Industrials': 'cyan', 'Consumer Staples': 'lime', 'Materials': 'brown',
    'Consumer Discretionary': 'pink', 'Real Estate': 'gray'
}
# 수정: 섹터 위치 간격 1.5로 확대 (균등 분배)
sector_positions = {sector: i * 1.5 for i, sector in enumerate(sector_colors.keys())}

def create_bubble_chart(period='ytd', end_date=None, specified_tickers=None):
    try:
        logging.info("Starting create_bubble_chart...")
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        df_tickers = get_sp500_tickers()
        tickers = df_tickers['Ticker'].tolist() + ['SPY']
        df_spy = pd.DataFrame({'Ticker': ['SPY'], 'Sector': ['Index']})
        df = pd.concat([df_tickers, df_spy], ignore_index=True)
        
        market_caps = get_market_caps(tickers)
        df['MarketCap'] = df['Ticker'].map(market_caps)
        df = df.dropna(subset=['MarketCap'])
        
        if period == 'ytd':
            start_date = f"{datetime.now().year}-01-01"
        else:
            days = {'1d': 1, '5d': 5, '1mo': 30, '1y': 365}.get(period, 365)
            start_date = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # 기간별 interval 동적 설정 (yfinance 제한 고려)
        if period in ['1d', '5d']:
            interval = '1m'
        elif period == '1mo':
            interval = '5m'
        else:  # ytd, 1y
            interval = '1h'
        logging.info(f"Using interval: {interval} for period {period}")
        
        data = download_data(tickers, start_date, end_date, interval)
        
        data.index = pd.to_datetime(data.index)
        data.index.name = 'Date'  # 명시적 설정
        
        returns = ((data / data.iloc[0]) - 1) * 100
        returns = returns.reset_index().melt(id_vars='Date', var_name='Ticker', value_name='Return')
        returns = returns.merge(df[['Ticker', 'Sector', 'MarketCap']], on='Ticker')
        
        # 수정: Return clip to -10 ~ 10 for visualization
        original_returns = returns['Return'].copy()  # hover용 원본 보존
        returns['Return'] = np.clip(returns['Return'], -10, 10)
        returns['OriginalReturn'] = original_returns  # 추가: hover용 열
        logging.info("Clipped returns for extreme values to +/-10%.")
        
        # 수정: jitter 범위 좁혀 섹터 내 공간 확대 (-0.2 ~ 0.2)
        df['jitter'] = np.random.uniform(-0.2, 0.2, len(df))
        returns = returns.merge(df[['Ticker', 'jitter']], on='Ticker')
        returns['x_pos'] = returns['Sector'].map(sector_positions) + returns['jitter']
        returns.loc[returns['Ticker'] == 'SPY', 'x_pos'] = -1
        
        min_market_cap = returns['MarketCap'].min()
        # 수정: 버블 크기 *3으로 축소 (최대 72)
        returns['Size'] = np.sqrt(returns['MarketCap'] / min_market_cap) * 3
        returns['Size'] = np.clip(returns['Size'], a_min=2, a_max=72)
        
        logging.info("Starting to add labels for top market caps...")
        returns['Label'] = ''  # 초기화
        specified_tickers_set = set(specified_tickers.split(',')) if specified_tickers else set()
        if specified_tickers_set:
            logging.info(f"Specified tickers for labels: {specified_tickers_set}")
            returns['IsSpecified'] = returns['Ticker'].isin(specified_tickers_set)
        else:
            returns['IsSpecified'] = False
            logging.info("No specified tickers, using default labels only.")
        grouped = returns.groupby('Date')
        for date, group in tqdm(grouped, desc="Adding labels for top market caps..."):
            large_mask = group['MarketCap'] > 5e11
            specified_mask = group['Ticker'].isin(specified_tickers_set)
            top_mask = large_mask | specified_mask
            # extreme return 라벨 추가
            for idx in group[top_mask].index:
                ticker = returns.loc[idx, 'Ticker']
                actual_ret = returns.loc[idx, 'OriginalReturn']
                label = ticker
                if actual_ret > 10:
                    label += " >10%"
                elif actual_ret < -10:
                    label += " <-10%"
                returns.loc[idx, 'Label'] = label
        logging.info("Finished adding labels for top market caps.")
        
        dates = sorted(returns['Date'].unique())
        
        # 600 프레임으로 1분 애니메이션 (100ms/frame)
        target_frames = 600
        frame_duration = 100
        transition_duration = 0
        if len(dates) >= target_frames:
            indices = np.linspace(0, len(dates) - 1, target_frames, dtype=int)
            sampled_dates = [dates[i] for i in indices]
        else:
            full_start = dates[0]
            full_end = dates[-1]
            step = (full_end - full_start) / (target_frames - 1)
            sampled_dates = [full_start + timedelta(seconds=i * step.total_seconds()) for i in range(target_frames)]
        logging.info(f"Sampled {len(sampled_dates)} frames from {len(dates)} original dates for 60s animation.")
        
        # first_date의 closest 매핑
        first_date = sampled_dates[0]
        idx_first = bisect.bisect_left(dates, first_date)
        if idx_first == 0:
            closest_first = dates[0]
        elif idx_first == len(dates):
            closest_first = dates[-1]
        else:
            before = dates[idx_first - 1]
            after = dates[idx_first]
            if (first_date - before) < (after - first_date):
                closest_first = before
            else:
                closest_first = after
        df_first = returns[returns['Date'] == closest_first]
        spy_return_first = df_first[df_first['Ticker'] == 'SPY']['Return'].values[0]
        title_first = f"S&P 500 Bubble Chart ({period.upper()} Returns to {end_date}) | Date/Time: {closest_first} | SPY {spy_return_first:.1f}%"
        
        fig = go.Figure()
        # 기본 버블 trace (markers only)
        fig.add_trace(go.Scatter(
            x=df_first['x_pos'],
            y=df_first['Return'],
            mode='markers',
            marker=dict(size=df_first['Size'], color=df_first['Sector'].map(sector_colors), line=dict(width=1, color='black')),
            hovertext=df_first['Ticker'],
            customdata=df_first['OriginalReturn'],  # 추가: actual return
            hovertemplate='Ticker: %{hovertext}<br>Clipped Return: %{y:.1f}%<br>Actual Return: %{customdata:.1f}%<br>Sector: %{marker.color}',  # 수정: customdata 사용
            name='Bubble'
        ))
        # 라벨 trace (text only, 중앙 위치)
        fig.add_trace(go.Scatter(
            x=df_first['x_pos'],
            y=df_first['Return'],
            mode='text',
            text=df_first['Label'],
            textposition='middle center',
            textfont=dict(
                size=df_first['IsSpecified'].map({True: 12, False: 10}).tolist(),
                family=df_first['IsSpecified'].map({True: 'bold Arial', False: 'Arial'}).tolist(),
                color=df_first['IsSpecified'].map({True: 'red', False: 'black'}).tolist()
            ),
            showlegend=False
        ))
        # 지정 티커를 위한 별표 trace (버블 위, 노란색 별 with 검정 테두리)
        specified_mask_first = df_first['IsSpecified']
        if specified_mask_first.any():
            fig.add_trace(go.Scatter(
                x=df_first['x_pos'][specified_mask_first],
                y=df_first['Return'][specified_mask_first] + 2,  # 버블 위 오프셋
                mode='markers',
                marker=dict(
                    symbol='star',  # 별표 심볼
                    size=15,  # 작은 크기
                    color='yellow',
                    line=dict(color='black', width=1)  # 검정 테두리
                ),
                hovertext=df_first['Ticker'][specified_mask_first] + ' Highlighted',
                showlegend=False
            ))
        
        # 수정: xaxis_range 확대 (섹터 간격 1.5 기준)
        max_x = len(sector_positions) * 1.5 + 2
        fig.update_layout(title=title_first,
                          xaxis={'tickvals': list(sector_positions.values()), 'ticktext': list(sector_positions.keys())},
                          xaxis_range=[-2, max_x],
                          yaxis_range=[-10, 10],  # ±10% 최상단/최하단
                          transition={'duration': transition_duration})
        
        # 수정: 제한선(hline) 완전 제거
        
        frames = []
        for date in sampled_dates:
            # closest original date 찾기 (bisect로 효율적)
            idx = bisect.bisect_left(dates, date)
            if idx == 0:
                closest_date = dates[0]
            elif idx == len(dates):
                closest_date = dates[-1]
            else:
                before = dates[idx - 1]
                after = dates[idx]
                if (date - before) < (after - date):
                    closest_date = before
                else:
                    closest_date = after
            df_frame = returns[returns['Date'] == closest_date]
            spy_return = df_frame[df_frame['Ticker'] == 'SPY']['Return'].values[0]
            frame_title = f"S&P 500 Bubble Chart ({period.upper()} Returns to {end_date}) | Date/Time: {closest_date} | SPY {spy_return:.1f}%"
            
            frame_data = [
                go.Scatter(
                    x=df_frame['x_pos'],
                    y=df_frame['Return'],
                    mode='markers',
                    marker=dict(size=df_frame['Size'], color=df_frame['Sector'].map(sector_colors), line=dict(width=1, color='black')),
                    hovertext=df_frame['Ticker'],
                    customdata=df_frame['OriginalReturn'],  # 추가
                    hovertemplate='Ticker: %{hovertext}<br>Clipped Return: %{y:.1f}%<br>Actual Return: %{customdata:.1f}%<br>Sector: %{marker.color}'  # 수정
                )
            ]
            # 라벨 trace
            frame_data.append(go.Scatter(
                x=df_frame['x_pos'],
                y=df_frame['Return'],
                mode='text',
                text=df_frame['Label'],
                textposition='middle center',
                textfont=dict(
                    size=df_frame['IsSpecified'].map({True: 12, False: 10}).tolist(),
                    family=df_frame['IsSpecified'].map({True: 'bold Arial', False: 'Arial'}).tolist(),
                    color=df_frame['IsSpecified'].map({True: 'red', False: 'black'}).tolist()
                ),
                showlegend=False
            ))
            # 별표 trace
            specified_mask_frame = df_frame['IsSpecified']
            if specified_mask_frame.any():
                frame_data.append(go.Scatter(
                    x=df_frame['x_pos'][specified_mask_frame],
                    y=df_frame['Return'][specified_mask_frame] + 2,
                    mode='markers',
                    marker=dict(
                        symbol='star',
                        size=15,
                        color='yellow',
                        line=dict(color='black', width=1)
                    ),
                    hovertext=df_frame['Ticker'][specified_mask_frame] + ' Highlighted',
                    showlegend=False
                ))
            
            frame = go.Frame(
                data=frame_data,
                layout=go.Layout(title=frame_title),
                name=str(date)
            )
            frames.append(frame)
        
        fig.frames = frames
        
        # 슬라이더 steps를 sampled_dates로, 100ms/0ms 맞춤
        sliders = [dict(
            steps=[dict(method='animate', args=[[str(date)], dict(mode='immediate', frame=dict(duration=frame_duration, redraw=True), transition=dict(duration=transition_duration))], label=str(date)) for date in sampled_dates],
            transition=dict(duration=transition_duration),
            currentvalue=dict(font=dict(size=12), prefix='Date/Time: ', visible=True),
            len=1.0
        )]
        
        fig.update_layout(sliders=sliders,
                          updatemenus=[dict(type='buttons', showactive=False,
                                            buttons=[dict(label='Play', method='animate', args=[None, dict(frame=dict(duration=frame_duration, redraw=True), transition=dict(duration=transition_duration), fromcurrent=True)]),
                                                     dict(label='Pause', method='animate', args=[[None], dict(frame=dict(duration=0, redraw=False), mode='immediate', transition=dict(duration=0))])])])
        
        cap_sizes = [3e12, 1e12, 5e11]
        cap_labels = ['3000Bn', '1000Bn', '500Bn']
        # 수정: Market Cap 범례 위치를 새로운 x 범위에 맞춤 (max_x + i*1.5)
        for i, cap in enumerate(cap_sizes):
            radius = np.sqrt(cap / min_market_cap) * 40 / 2
            fig.add_shape(type='circle', 
                          xref='x', yref='y',
                          x0=max_x + i*1.5 - radius/100,
                          x1=max_x + i*1.5 + radius/100,
                          y0=10 + 5,  # y max 10 기준
                          y1=10 + 5 + radius/50,
                          fillcolor='gray', opacity=0.5, line_color='gray')
        fig.add_annotation(text='Market Cap: ' + ' '.join(cap_labels), 
                           x=max_x + 1.5, 
                           y=10 + 10,  # 수정
                           showarrow=False, font_size=10)
        
        html_file = f'sp500_bubble_chart_{period}_{end_date}.html'
        fig.write_html(html_file)
        logging.info(f"Interactive chart saved as {html_file}")
    except Exception as e:
        logging.error(f"Error in create_bubble_chart: {e}", exc_info=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="S&P 500 Bubble Chart Generator")
    parser.add_argument('--period', type=str, default='ytd', choices=['ytd', '1d', '5d', '1mo', '1y'], help="Period for data (default: ytd)")
    parser.add_argument('--end_date', type=str, default=None, help="End date in YYYY-MM-DD (default: today)")
    parser.add_argument('--tickers', type=str, default=None, help="Comma-separated tickers to highlight labels (e.g., AAPL,MSFT)")
    args = parser.parse_args()
    
    create_bubble_chart(args.period, args.end_date, args.tickers)
