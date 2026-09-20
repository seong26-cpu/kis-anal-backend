# -*- coding: utf-8 -*-
"""
app.py
======
마켓레이더 대시보드용 Flask 백엔드.

절대 원칙
---------
1. KIS_APP_KEY / KIS_APP_SECRET 은 이 파일이나 프런트엔드(HTML)에 절대 하드코딩하지 않는다.
   반드시 환경변수(.env 또는 배포 플랫폼의 환경변수 설정)로만 주입한다.
2. 프런트엔드(trading-terminal-step*.html)는 이 서버의 /api/* 엔드포인트만 호출한다.
   KIS 실전 API는 이 서버에서만 직접 호출한다 — 브라우저에서 KIS로 직접 요청하지 않는다.
3. case_engine.py / closing_bet.py 의 원칙을 그대로 따른다: 라이브 데이터가 없으면
   "판단불가"를 그대로 반환하고, 숫자를 임의로 채우지 않는다.

실행 방법
---------
1) 같은 폴더에 기존에 갖고 계신 case_engine.py, closing_bet.py 를 복사해 넣는다.
   (news_client.py / dart_client.py / market_context.py / config_store.py 도 함께 —
    없으면 이 폴더의 스텁 버전을 우선 사용하고, 준비되는 대로 실제 구현으로 교체)
2) pip install -r requirements.txt
3) .env.example 을 .env 로 복사 후 실전 키 입력 (절대 git에 커밋하지 말 것)
4) python app.py  → http://localhost:5000
"""

import os
from flask import Flask, jsonify, request
from flask_cors import CORS

import config_store
import kis_client
from case_engine import evaluate_case, rank_top5, CASE_PRIORITY_ORDER
from closing_bet import evaluate_closing_bet_candidate, rank_closing_bet_candidates

app = Flask(__name__)
# 개발 중에는 전체 허용, 배포 시 ALLOWED_ORIGIN 환경변수로 프런트엔드 도메인만 허용 권장
CORS(app, origins=os.environ.get("ALLOWED_ORIGIN", "*"))

# 세력추적 CASE / 종가배팅 스캔 대상 종목 리스트 (감시 리스트) — 필요에 맞게 수정
WATCHLIST = ["005930", "000660", "042700", "373220", "091990"]


@app.route("/api/health")
def health():
    """서버 동작 + KIS 키 설정 여부만 확인 (키 값 자체는 절대 반환하지 않음)"""
    return jsonify({
        "ok": True,
        "kis_key_configured": config_store.has_kis_keys(),
    })


@app.route("/api/market-signal")
def market_signal():
    """시장 신호등 + 지수 + 수급. 실전 연동 시 kis_client에서 지수/수급 실측값을 채운다."""
    data = kis_client.get_market_overview()
    if data is None:
        return jsonify({"error": "판단불가", "reason": "KIS 지수/수급 데이터 조회 실패 또는 키 미설정"}), 200
    return jsonify(data)


@app.route("/api/stock/<code>")
def stock_detail(code):
    """종목 상세 (StockItem 스키마) — 프런트엔드 종목분석 탭이 그대로 소비할 수 있는 형태로 반환"""
    snap = kis_client.get_live_snapshot(code)
    if snap is None:
        return jsonify({"error": "판단불가", "reason": f"{code} 라이브 데이터 조회 실패"}), 200
    return jsonify(kis_client.snapshot_to_stock_item(snap))


@app.route("/api/case-scan", methods=["GET", "POST"])
def case_scan():
    """WATCHLIST 전체에 대해 CASE 1~11을 평가하고, 우선순위 규칙대로 TOP5를 반환"""
    verdicts_by_case = {cid: [] for cid in CASE_PRIORITY_ORDER}
    errors = []
    for code in WATCHLIST:
        snap = kis_client.get_live_snapshot(code)
        if snap is None:
            errors.append(code)
            continue
        for cid in CASE_PRIORITY_ORDER:
            verdicts_by_case[cid].append(evaluate_case(cid, snap))
    top5 = rank_top5(verdicts_by_case)
    return jsonify({
        "top5": [v.__dict__ for v in top5],
        "skipped_codes": errors,  # 데이터 조회 실패 종목 (임의로 채우지 않고 제외 처리했음을 투명하게 노출)
    })


@app.route("/api/closing-bet", methods=["GET", "POST"])
def closing_bet_scan():
    """WATCHLIST 전체에 대해 종가배팅 5조건+8품질검증을 평가하고 상위 N개를 반환"""
    candidates = []
    errors = []
    trading_value_top_codes, change_rate_top_codes = kis_client.get_top_rank_code_sets(WATCHLIST)
    for code in WATCHLIST:
        snap = kis_client.get_live_snapshot(code)
        if snap is None:
            errors.append(code)
            continue
        candidates.append(evaluate_closing_bet_candidate(
            snap,
            is_trading_value_top=code in trading_value_top_codes,
            is_change_rate_top=code in change_rate_top_codes,
        ))
    ranked = rank_closing_bet_candidates(candidates, top_n=10)
    return jsonify({
        "candidates": [c.__dict__ for c in ranked],
        "skipped_codes": errors,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
