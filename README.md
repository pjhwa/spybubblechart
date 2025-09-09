# S&P 500 Bubble Chart Generator

S&P 500 지수 구성 종목의 주식 데이터를 기반으로 한 동적 버블 차트를 생성하는 Python 스크립트를 제공합니다. 버블 차트는 각 종목의 시가총액(MarketCap)에 비례한 버블 크기, 섹터별 위치 배치, 지정 기간 동안의 수익률(Return) 변화를 애니메이션으로 시각화합니다. SPY( S&P 500 ETF)를 기준으로 전체 시장 수익률도 표시하며, Plotly 라이브러리를 사용하여 인터랙티브 HTML 파일을 출력합니다. 이 도구는 금융 데이터 분석, 시장 트렌드 관찰, 또는 교육 목적으로 유용합니다.

![sp500_bubble_chart](https://github.com/user-attachments/assets/f2d3aa77-54df-4b0c-a3e0-f99163f6465b)

코드의 주요 특징:
- **캐싱 지원**: 티커 목록, market cap, 가격 데이터를 캐시 파일(.pkl)로 저장하여 반복 실행 시 다운로드 시간을 절약합니다. 동일 옵션으로 실행하면 기존 캐시를 사용합니다.
- **청크 다운로드**: yfinance를 통해 대량 데이터를 안정적으로 가져오며, 오류 재시도(retries)와 청크 처리(chunksize=20)를 적용했습니다.
- **애니메이션 기능**: 시간/날짜별 수익률 변화 애니메이션, 슬라이더 및 Play/Pause 버튼 지원.
- **라벨 및 hover**: 대형주(시가총액 > 500B USD)만 버블 내에 티커 라벨 표시, 모든 버블에 마우스 오버 시 티커/수익률/섹터 정보 표시.
- **market cap 범례**: 상단에 3단계(3000Bn, 1000Bn, 500Bn) 원형 범례 표시.
- **로깅 및 진행바**: logging으로 과정 추적, tqdm으로 장시간 루프(라벨 추가 등) 진행 상태 표시.

이 코드는 2025-09-06 기준으로 테스트되었으며, yfinance API의 안정성을 기반으로 합니다. 실제 사용 시 시장 데이터 변동성을 고려하세요.

## 요구사항 (Prerequisites)

- **Python 버전**: Python 3.8 이상 (테스트 환경: Python 3.12.3).
- **필요 라이브러리**: 아래 목록을 `requirements.txt` 파일로 저장하고 설치하세요.
  ```
  yfinance
  pandas
  plotly
  numpy
  requests
  tqdm
  ```
  설치 명령어: `pip install -r requirements.txt`
- **인터넷 연결**: Wikipedia와 yfinance API 접근 필요 (캐시 사용 시 생략 가능).
- **주의**: 추가 패키지 설치 불가 (예: pip install 불필요 라이브러리). 코드 내 import로 모든 라이브러리 처리.

## 설치 (Installation)

1. 리포지토리 클론:
   ```
   git clone https://github.com/pjhwa/spybubblechart.git
   cd spybubblechart
   ```

2. requirements.txt 생성 및 설치:
   위 목록을 requirements.txt에 저장한 후:
   ```
   pip install -r requirements.txt
   ```

3. 캐시 파일: 스크립트 실행 시 자동 생성 (sp500_tickers.pkl, market_caps.pkl, price_data_*.pkl).

## 사용법 (Usage)

스크립트는 명령줄 인자를 통해 실행합니다. 기본 파일명: `sp500_bubble_chart.py`.

### 명령어 예시
```
python3 sp500_bubble_chart.py --period 1d --end_date 2025-09-06
```
- 출력: `sp500_bubble_chart_1d_2025-09-06.html` 파일 생성. 브라우저에서 열어 애니메이션 확인.
- 로그: 터미널과 `sp500_log.txt`에 기록.

### 인자 설명
- `--period`: 데이터 기간 선택 (default: ytd).
  - 옵션: ytd (올해 시작부터), 1d (1일, 분 단위 데이터), 5d (5일), 1mo (1개월), 1y (1년).
- `--end_date`: 종료 날짜 (YYYY-MM-DD 형식, default: 오늘 날짜).
  - 예: 2025-09-06 – 해당 날짜까지 데이터 가져옴.

### 실행 흐름
1. **티커 목록 로드**: Wikipedia에서 S&P 500 티커와 섹터 가져오거나 캐시 사용.
2. **market cap 로드**: yfinance로 각 티커의 시가총액 가져오거나 캐시 사용.
3. **가격 데이터 로드**: 지정 기간 데이터 다운로드 (yfinance, Adj Close 기준). 캐시 있으면 스킵. 청크(20개 티커) 단위로 처리해 오류 방지.
4. **데이터 처리**: 수익률 계산 ((현재 / 시작) - 1) * 100. jitter 추가로 버블 위치 랜덤화 (중첩 방지).
5. **라벨 추가**: 대형주에만 티커 라벨. tqdm 프로그레스바로 진행 표시 (예: "Adding labels...: 100%|██████████| 390/390 [00:00<00:00, 1500it/s]").
6. **Plotly 차트 생성**: go.Scatter로 버블, frames로 애니메이션, sliders/updatemenus로 인터랙션.
7. **범례 추가**: market cap 3단계 원형 표시 (크기 비례).
8. **출력 저장**: HTML 파일로 저장.

### 예시 출력 화면
- 타이틀: "S&P 500 Bubble Chart (1D Returns to 2025-09-06) | Date/Time: 2025-09-05 14:17:00+00:00 | SPY -0.5%"
- X축: 섹터 (Energy, Health Care 등).
- Y축: 수익률 (%).
- 버블: 크기 = sqrt(MarketCap / min) * 40 (clip 2~120), 색상 = 섹터별.
- Hover: "Ticker: [티커]<br>Return: [수익률]%<br>Sector: [색상]".
- 슬라이더: 날짜/시간 이동.
- 버튼: Play/Pause.

## 코드 구조 (Code Structure)

코드 파일: `sp500_bubble_chart.py`

- **임포트**: yfinance (데이터 다운로드), pandas (데이터 처리), plotly (차트), numpy (수학), tqdm (진행바), logging (로그).
- **함수**:
  - `get_sp500_tickers()`: Wikipedia에서 티커/섹터 데이터프레임 반환. 캐시 지원.
  - `download_data(tickers, start_date, end_date, interval, chunksize)`: 가격 데이터 다운로드. 캐시 우선, 청크 처리, ffill/bfill로 결측치 보완.
  - `get_market_caps(tickers)`: 각 티커의 marketCap 가져옴. 캐시 지원.
  - `create_bubble_chart(period, end_date)`: 주요 로직. 데이터 처리, Size 계산 (sqrt 스케일링), 라벨 추가 (tqdm), Plotly fig/frames 생성, HTML 저장.
- **sector_colors/positions**: 섹터별 색상/위치 딕셔너리 (고정).
- **main**: argparse로 인자 파싱, create_bubble_chart 호출.

### 주요 로직 상세
- Size 계산: `np.sqrt(MarketCap / min_market_cap) * 40` – 제곱근으로 비례성 유지하면서 과도한 차이 완화. clip으로 렌더링 제한.
- jitter: `np.random.uniform(-0.4, 0.4)` – 섹터 내 버블 중첩 방지.
- 라벨: MarketCap > 500e9인 종목만 표시 (top_mask).
- 범례: cap_sizes에 따라 원형 shape 추가, 크기 비례 (sqrt 사용).
- 에러 핸들링: yfinance 다운로드 retries=3, time.sleep으로 지연.

## 성능 및 최적화 (Performance and Optimization)

- **실행 시간**: 캐시 사용 시 5-10초 (데이터 처리/Plotly 렌더링). 첫 실행 시 다운로드로 1-2분 소요 (505 티커).
- **메모리**: 대형 데이터(1d: ~390 타임스탬프) 처리 시 500MB 정도. pandas melt/groupby 최적화됨.
- **캐시 관리**: 캐시 파일 삭제로 새로 다운로드 (`rm *.pkl`).
- **테스트 환경**: macOS (iMac), Python 3.12. Broken pipe 오류 시 SSH keep-alive 옵션 추천 (`-o ServerAliveInterval=60`).

## 트러블슈팅 (Troubleshooting)

- **yfinance 오류**: "No timezone found" 또는 "PricesMissingError" – BRK.B, BF.B 같은 특수 티커. 로그 확인, 캐시 삭제 후 재실행.
- **Plotly 렌더링 문제**: HTML 파일 브라우저 호환성 – Chrome 추천. 버블 크기 과도 시 scale(40) 줄임.
- **데이터 결측**: ffill/bfill 적용됨. 시장 휴일 시 자동 bfill.
- **로그 확인**: `sp500_log.txt` – 다운로드 오류, chunk 처리 상세.
- **사용자 정의**: sector_colors 수정으로 색상 변경 가능. top_mask 임계값(5e11) 조정으로 더 많은 라벨 표시.

## 기여 (Contributing)

기여 환영합니다! Pull Request를 통해 버그 수정, 기능 추가 제안하세요. 예:
- 더 많은 기간 옵션 추가.
- 실시간 데이터 지원 (yfinance live).

## 라이선스 (License)

MIT License. 상세: LICENSE 파일 참조.
