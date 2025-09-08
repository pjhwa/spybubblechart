import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go  # 개선: frames 사용을 위해 import 추가
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
    cache_file = f'price_data_{start_date}_{end_date}_{interval}.pkl'
    if os.path.exists(cache_file):
        logging.info(f"Loading price data from cache: {cache_file} (skipping download as cache exists for identical options)")
        with open(cache_file, 'rb') as f:
            data = pickle.load(f)
        return data  # 캐시 존재 시 완전히 스킵
    
    # 캐시가 없을 때만 다운로드
    data = pd.DataFrame()
    current_date = datetime.now().strftime('%Y-%m-%d')
    end_date = min(end_date, current_date)
    
    new_start = data.index.max().strftime('%Y-%m-%d') if not data.empty else start_date
    if new_start >= end_date:
        return data
    
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
        logging.error("No valid data downloaded. Exiting.")
        raise ValueError("No valid data downloaded.")
    data.index.name = 'Date'
    with open(cache_file, 'wb') as f:
        pickle.dump(data, f)
    logging.info("Price data updated and cached.")
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
sector_positions = {sector: i for i, sector in enumerate(sector_colors.keys())}

def create_bubble_chart(period='ytd', end_date=None):
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
        
        interval = '1m' if period == '1d' else '1d'
        data = download_data(tickers, start_date, end_date, interval)
        
        data.index = pd.to_datetime(data.index)
        
        returns = ((data / data.iloc[0]) - 1) * 100
        returns = returns.reset_index().melt(id_vars='Date', var_name='Ticker', value_name='Return')
        returns = returns.merge(df[['Ticker', 'Sector', 'MarketCap']], on='Ticker')
        
        df['jitter'] = np.random.uniform(-0.4, 0.4, len(df))
        returns = returns.merge(df[['Ticker', 'jitter']], on='Ticker')
        returns['x_pos'] = returns['Sector'].map(sector_positions) + returns['jitter']
        returns.loc[returns['Ticker'] == 'SPY', 'x_pos'] = -1
        
        # 추가 개선: 버블 크기 차이 명확히 - 스케일링 15 -> 25로 증가, clip 3~80으로 조정
        min_market_cap = returns['MarketCap'].min()
        returns['Size'] = np.sqrt(returns['MarketCap'] / min_market_cap) * 25  # 15 -> 25로 증가하여 크기 차이 강조
        returns['Size'] = np.clip(returns['Size'], a_min=3, a_max=80)  # 최소 5->3, 최대 50->80으로 조정
        
        logging.info("Adding labels for top market caps...")
        returns['Label'] = ''
        grouped = returns.groupby('Date')
        for date, group in grouped:
            top_mask = group['MarketCap'] > 5e11
            returns.loc[group.index[top_mask], 'Label'] = group.loc[top_mask, 'Ticker']
        
        dates = sorted(returns['Date'].unique())
        
        first_date = dates[0]
        df_first = returns[returns['Date'] == first_date]
        spy_return_first = df_first[df_first['Ticker'] == 'SPY']['Return'].values[0]
        title_first = f"S&P 500 Bubble Chart ({period.upper()} Returns to {end_date}) | Date/Time: {first_date} | SPY {spy_return_first:.1f}%"
        
        fig = go.Figure(data=[go.Scatter(
            x=df_first['x_pos'],
            y=df_first['Return'],
            mode='markers+text',
            marker=dict(size=df_first['Size'], color=df_first['Sector'].map(sector_colors), line=dict(width=1, color='black')),
            text=df_first['Label'],
            textposition='middle center',
            textfont=dict(size=7),
            hovertext=df_first['Ticker'],  # 추가 개선: hovertext로 Ticker 설정 (작은 버블에서도 hover 시 표시)
            hovertemplate='Ticker: %{hovertext}<br>Return: %{y:.1f}%<br>Sector: %{marker.color}',  # 추가 개선: hovertemplate로 상세 표시
            name='Bubble'
        )])
        
        fig.update_layout(title=title_first,
                          xaxis={'tickvals': list(sector_positions.values()), 'ticktext': list(sector_positions.keys())},
                          xaxis_range=[-2, len(sector_positions)],
                          yaxis_range=[returns['Return'].min() - 5, returns['Return'].max() + 5],
                          transition={'duration': 300})
        
        frames = []
        for date in dates:
            df_frame = returns[returns['Date'] == date]
            spy_return = df_frame[df_frame['Ticker'] == 'SPY']['Return'].values[0]
            frame_title = f"S&P 500 Bubble Chart ({period.upper()} Returns to {end_date}) | Date/Time: {date} | SPY {spy_return:.1f}%"
            
            frame = go.Frame(
                data=[go.Scatter(
                    x=df_frame['x_pos'],
                    y=df_frame['Return'],
                    mode='markers+text',
                    marker=dict(size=df_frame['Size'], color=df_frame['Sector'].map(sector_colors), line=dict(width=1, color='black')),
                    text=df_frame['Label'],
                    textposition='middle center',
                    textfont=dict(size=7),
                    hovertext=df_frame['Ticker'],  # 추가 개선: hovertext로 Ticker 설정
                    hovertemplate='Ticker: %{hovertext}<br>Return: %{y:.1f}%<br>Sector: %{marker.color}'  # 추가 개선: hovertemplate로 상세 표시
                )],
                layout=go.Layout(title=frame_title),
                name=str(date)
            )
            frames.append(frame)
        
        fig.frames = frames
        
        sliders = [dict(
            steps=[dict(method='animate', args=[[str(date)], dict(mode='immediate', frame=dict(duration=300, redraw=True), transition=dict(duration=300))], label=str(date)) for date in dates],
            transition=dict(duration=300),
            currentvalue=dict(font=dict(size=12), prefix='Date/Time: ', visible=True),
            len=1.0
        )]
        
        fig.update_layout(sliders=sliders,
                          updatemenus=[dict(type='buttons', showactive=False,
                                            buttons=[dict(label='Play', method='animate', args=[None, dict(frame=dict(duration=300, redraw=True), transition=dict(duration=300), fromcurrent=True)]),
                                                     dict(label='Pause', method='animate', args=[[None], dict(frame=dict(duration=0, redraw=False), mode='immediate', transition=dict(duration=0))])])])
        
        # 3단계 Market Cap 범례 (이전 개선 유지)
        cap_sizes = [3e12, 1e12, 5e11]
        cap_labels = ['3000Bn', '1000Bn', '500Bn']
        for i, cap in enumerate(cap_sizes):
            radius = np.sqrt(cap / min_market_cap) * 25 / 2  # 스케일링과 맞춤
            fig.add_shape(type='circle', 
                          xref='x', yref='y',
                          x0=len(sector_positions) + i*1 - radius/100,
                          x1=len(sector_positions) + i*1 + radius/100,
                          y0=returns['Return'].max() + 15,
                          y1=returns['Return'].max() + 15 + radius/50,
                          fillcolor='gray', opacity=0.5, line_color='gray')
        fig.add_annotation(text='Market Cap: ' + ' '.join(cap_labels), 
                           x=len(sector_positions) + 1, 
                           y=returns['Return'].max() + 20, 
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
    args = parser.parse_args()
    
    create_bubble_chart(args.period, args.end_date)
