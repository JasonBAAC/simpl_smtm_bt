# SMTM-Lite (Simple Crypto Auto-Trading System) PRD

## 1. 프로젝트 개요
Bithumb 거래소의 데이터를 활용하여 사전에 정의된 전략에 따라 가상화폐를 자동으로 매수/매도하는 경량화된 자동거래 시스템입니다. 실시간 데이터 수신, 기술적 지표 분석, 병렬 거래 처리 및 텔레그램 알림 기능을 제공합니다.

## 2. 시스템 아키텍처
시스템은 크게 5가지 모듈과 이들을 제어하는 Operator로 구성됩니다.
- **Data Provider**: Bithumb API 및 웹소켓을 통한 실시간 시세 수신 및 저장 (SQLite).
- **Strategy**: 수신된 데이터를 바탕으로 매수 대상 자산을 선정 (이동평균 및 증가율 기반).
- **Trader**: 선정된 자산에 대한 매수/매도 실행 및 초정밀 주문 관리 (웹소켓 기반).
- **Analyzer**: 거래 성과 및 수익률 분석.
- **Operator**: 전체 시스템의 생명주기 관리 및 텔레그램 인터페이스 제공.

## 3. 주요 기능 요구사항

### 3.1. 모드 및 설정 (Arguments)
- **거래 모드**: 시뮬레이션(가상 거래) vs 실제 거래(Bithumb API 연동).
- **데이터 저장**: API 수신 데이터를 SQLite DB에 저장할지 여부 결정.
- **운영 설정**: 최대 거래 종목 수 (n), 총 투입 금액, 수수료(%), 알림 여부(--msg) 등.

### 3.2. Data Provider (실시간 스트리밍)
- **Websocket 연동**: `pybithumb.WebSocketManager`를 통해 전 종목의 시세를 ms 단위로 실시간 수신.
- **데이터 샘플링**: 전략 수행을 위해 5초 주기로 실시간 데이터를 스냅샷 찍어 제공.
- **데이터 저장**: 샘플링된 데이터를 자산별로 SQLite에 저장. 시작 시 DB 초기화.

### 3.3. Strategy (매수 전략 최적화)
- **지표 계산**:
    - `price_rate`: 5초 전 종가 대비 현재가 증가율 (최소 0.1% 이상 유의미한 상승 시에만 고려).
    - `units_rate`: 5초 전 거래량 대비 현재 거래량 증가율 (최소 50% 이상 폭증 시에만 고려).
    - `Relative Volume (RV)`: 최근 4구간 평균 거래량 대비 현재 유의미한 거래량 폭발 확인.
- **필터링 로직**:
    - **Volatility Filter**: 단기 표준편차를 활용해 과도하게 불안정한 급등락 종목 제외.
    - **Trend Alignment**: 단기(20초) 및 중기(1분) 이동평균선이 모두 우상향인 정배열 상태 확인.
- **자산 선정 (Pocket)**:
    - 20초간 5초 간격 3구간 윈도우잉 및 상기 필터링 수행.
    - 필터를 통과한 종목 중 MA 값이 큰 상위 n개 선정.

### 3.4. Trader (거래 실행 및 초정밀 감시)
- **매수**: 
    - **Slippage Control**: 매수 요청 시점 시세 대비 0.2% 이상 급등 시 체결 포기 (고점 추격 방지).
    - 1회 매수 금액 = `총 투입금액 / n`.
- **매도**:
    - **실시간 감시**: 웹소켓 데이터를 활용하여 **0.1초(100ms)** 주기로 익절/손절 여부를 확인.
    - **Trailing Stop**: 0.5% 수익 도달 후 고점 대비 0.2% 하락 시 이익 보존 매도.
    - **Stagnation Exit**: 30초 이상 가격 정체(변동성 0.05% 이내) 시 조기 탈출.
    - **손절/익절 조정**: 순수익률 기준 손절 -0.2%, 익절 0.7% (분석 데이터 기반 최적화).
    - **Time-out**: 매수 후 1분 경과 시 강제 매도.
- **운영 방식**:
    - **Parallel Slot Rotation**: 비어 있는 슬롯 발생 시 즉시 신규 종목 투입하여 회전율 극대화.

### 3.5. Operator & Logging
- **Notification Policy**: `--msg` 옵션으로 알림 여부 선택. 단, 거래 개시/종료/긴급정지 알림은 항상 전송.
- **Circuit Breaker**: 누적 수익률 -5% 도달 시 즉시 모든 거래 중단 및 시스템 종료.
- **Dual Logging**: 전체 운영 로그(`smtm_...`)와 전략 선정 상세 로그(`pocket_...`) 이원화. 2MB 로테이션.

## 4. 기술 스택
- **Language**: Python 3.x
- **Exchange API**: `pybithumb` (Websocket 지원)
- **Database**: SQLite
- **Concurrency**: `threading`, `queue` (Telegram Msg Queue)
- **Notification**: `python-telegram-bot` (Thread-safe)

## 5. 단계별 워크플로우
1. **Initialize**: Argument 파싱, .env 로드, DB 초기화 및 로그 설정.
2. **Websocket Start**: 전 종목 실시간 시세 수신 쓰레드 기동.
3. **Main Loop**: 5초 주기로 데이터 샘플링, 전략 업데이트 및 슬롯 확인.
4. **Trading**: 빈 슬롯 발생 시 신규 매수, `Worker` 쓰레드에서 0.1초 주기로 실시간 매도 감시.
5. **Reporting**: 텔레그램 및 이원화된 로그 파일을 통한 실시간 모니터링 및 성과 분석.
