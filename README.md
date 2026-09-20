# 마켓레이더 (Flask 백엔드 + 프런트엔드 통합 배포)

이제 `backend/` 폴더 하나만 Render에 올리면, **그 주소 하나로 화면(UI)과 KIS API가 전부 동작**합니다.
`static/index.html`이 프런트엔드 전체이고, Flask가 `/`에서 이 파일을 직접 서빙합니다.
(이전에 `https://.....onrender.com/`에서 Not Found가 난 이유: static/index.html과 "/" 라우트가 없었기 때문 — 이번에 추가함)

## 1) 로컬 실행
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # KIS_APPKEY / KIS_APPSECRET / KIS_CANO / KIS_ACNT_PRDT_CD 입력
python app.py
```
브라우저로 `http://localhost:5000` 접속 → 화면이 바로 뜹니다 (더 이상 html 파일을 따로 열 필요 없음).

## 2) Render 재배포 (기존 서비스에 이번 수정분 반영)
1. 이 `backend/` 폴더 전체(= 이번에 받은 backend.zip 압축 해제한 내용)를 기존 GitHub 저장소에 덮어쓰기
   - `git add . && git commit -m "serve frontend from Flask" && git push`
2. Render는 push하면 자동으로 재배포됩니다 (Auto-Deploy 켜져 있을 시)
   - 수동이라면 Render 대시보드 → Manual Deploy → Deploy latest commit
3. Environment 변수(`KIS_APPKEY` 등)는 이미 등록되어 있다면 그대로 유지됩니다
4. 배포 완료 후 `https://kis-anal-backend-1.onrender.com/` 접속 → 화면이 떠야 정상

## 3) PC / 휴대폰 어디서나 접속
- 이제 **PC와 휴대폰 모두 같은 주소** `https://kis-anal-backend-1.onrender.com/` 하나만 열면 됩니다
- 프런트엔드가 백엔드와 같은 도메인에서 서빙되므로, API_BASE를 따로 설정할 필요가 없습니다(자동 인식)
- 우측 상단 ⚙ 버튼은 "프런트와 백엔드를 서로 다른 곳에 각각 배포하는 경우"에만 필요합니다

## 4) 확인해야 할 TODO
- `kis_client.py`: 투자자매매동향(수급) API TR_ID는 apiportal 공식문서에서 최종 확인 후 구현
- `kis_client.snapshot_to_stock_item()`: RS/MTT/재무추정/차트 시계열 계산 로직 연결
- `news_client.py` / `dart_client.py`: 실제 API 연동 (키 없으면 자동으로 "판단불가" 처리됨)
- `market_context.py`: KOSDAQ 지수 실측 조회 방식 확정
- 프런트엔드를 수정할 때는 `backend/static/index.html`을 직접 편집하면 됩니다 (배포되는 실제 화면)
