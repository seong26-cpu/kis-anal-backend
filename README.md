# 마켓레이더 백엔드 (Flask)

프런트엔드(`trading-terminal-step5.html`)는 이 서버의 `/api/*` 만 호출합니다.
KIS 실전 API 키는 **이 서버에서만** 다루고, 프런트엔드(브라우저)에는 절대 넣지 않습니다.

## 1) 로컬 실행
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # .env를 열어 KIS_APPKEY / KIS_APPSECRET / KIS_CANO / KIS_ACNT_PRDT_CD 입력
python app.py           # http://localhost:5000
curl http://localhost:5000/api/health   # {"ok":true,"kis_key_configured":true} 확인
```
`case_engine.py`, `closing_bet.py`는 이미 이 폴더에 복사되어 있습니다(업로드하신 원본 그대로).

## 2) 프런트엔드 연결
`trading-terminal-step5.html`은 이미 `fetch` 연동이 되어 있습니다.
- 브랜드바의 상태 배지가 "● 백엔드 연결됨"으로 바뀌면 정상 연결
- 종목분석 탭: 종목 클릭 시 `GET /api/stock/<code>` 호출 → 가격/등락률/거래대금만 실시간 반영 (RS/MTT/차트는 아직 TODO, Mock 유지)
- 세력추적 CASE / 종가배팅 탭: "⟳ 백엔드 실시간 스캔 실행" 버튼 클릭 시 `POST /api/case-scan`, `POST /api/closing-bet` 호출
- 배포 후에는 파일 상단의 `const API_BASE = 'http://localhost:5000'` 를 배포 주소로 변경

## 3) 배포 (Render.com — 기존 세력추적 앱과 동일 패턴)
1. `git init && git add . && git commit -m "init"` (backend 폴더 기준)
   - `.gitignore`에 `.env`가 포함되어 있는지 반드시 확인 (`git status`에 .env가 안 보여야 정상)
2. GitHub 저장소 생성 후 `git remote add origin <repo-url> && git push -u origin main`
3. Render → New Web Service → 방금 만든 저장소 연결, Root Directory를 `backend`로 지정
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `python app.py`
6. Environment → `.env`에 적었던 항목(`KIS_APPKEY`, `KIS_APPSECRET`, `KIS_CANO`, `KIS_ACNT_PRDT_CD`, `KIS_MODE` 등)을
   Render 환경변수로 동일하게 등록 (⚠️ 코드/저장소에는 값을 절대 넣지 않음)
7. 배포 완료 후 프런트엔드 `API_BASE`를 Render가 발급한 URL로 교체하고,
   `trading-terminal-step5.html`은 GitHub Pages 등 정적 호스팅에 올리기
8. 배포 시 `ALLOWED_ORIGIN`을 프런트엔드 실제 도메인으로 제한 권장 (CORS)

## 4) 확인해야 할 TODO
- `kis_client.py`: 투자자매매동향(수급) API TR_ID는 apiportal 공식문서에서 최종 확인 후 구현
- `kis_client.snapshot_to_stock_item()`: RS/MTT/재무추정/차트 시계열 계산 로직 연결
- `news_client.py` / `dart_client.py`: 실제 API 연동 (키 없으면 자동으로 "판단불가" 처리됨)
- `market_context.py`: KOSDAQ 지수 실측 조회 방식 확정
