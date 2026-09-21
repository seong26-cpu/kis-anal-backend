# -*- coding: utf-8 -*-
"""
app.py
======
마켓레이더 대시보드용 Flask 백엔드.
GET / 로 접속하면 static/index.html(프런트엔드 전체)을 그대로 서빙합니다.
→ Render에 이 backend 폴더 하나만 배포하면, 그 주소 하나로 PC/휴대폰 어디서든
  화면(UI)과 API(KIS 데이터)가 전부 동작합니다.

절대 원칙
---------
1. KIS_APPKEY / KIS_APPSECRET 은 이 파일이나 프런트엔드(HTML)에 절대 하드코딩하지 않는다.
   반드시 환경변수(.env 또는 배포 플랫폼의 환경변수 설정)로만 주입한다.
2. 프런트엔드(static/index.html)는 이 서버의 /api/* 엔드포인트만 호출한다.
3. case_engine.py / closing_bet.py 의 원칙을 그대로 따른다: 라이브 데이터가 없으면
   "판단불가"를 그대로 반환하고, 숫자를 임의로 채우지 않는다.

감시 유니버스(스캔 대상) 관련
------------------------------
- 거래대금 순위(FHPST01710000) + 등락률 순위(FHPST01700000) API로 실시간 상위 종목을
  동적으로 가져온다(get_watchlist). 순위 API 호출이 실패하면(키 미설정 등) 정적
  FALLBACK_WATCHLIST(5종목)로 자동 대체된다.
- SCAN_LIMIT 환경변수로 "실제 상세 평가"할 종목 수를 제한한다(기본 30).
  이유: CASE/종가배팅 평가 1종목당 KIS API를 2회씩 호출하므로, 100종목을 전부
  평가하면 최대 200회 호출 + 순차 처리 시간이 길어져 KIS 초당 호출 제한과 Render
  요청 타임아웃에 걸릴 수 있다. 순위 유니버스 자체는 최대 100종목까지 넓게 가져오되,
  "상세 평가"는 그중 상위 SCAN_LIMIT개만 수행한다 (필요시 .env에서 조정).
"""

import os
import time
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import config_store
import kis_client
import market_data_crawler
from case_engine import evaluate_case, rank_top5, CASE_PRIORITY_ORDER
from closing_bet import evaluate_closing_bet_candidate, rank_closing_bet_candidates

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app, origins=os.environ.get("ALLOWED_ORIGIN", "*"))

FALLBACK_WATCHLIST = ["005930", "000660", "042700", "373220", "091990"]
UNIVERSE_LIMIT = int(os.environ.get("UNIVERSE_LIMIT", "100"))   # 순위 유니버스 크기
SCAN_LIMIT = int(os.environ.get("SCAN_LIMIT", "30"))            # 실제 상세평가 개수(레이트리밋 보호)
_CALL_DELAY_SEC = 0.05


def get_watchlist(limit: int = SCAN_LIMIT):
    """거래대금·등락률 상위 유니버스에서 상위 limit개. 순위 API 실패 시 고정 5종목으로 대체."""
    universe = kis_client.get_scan_universe(UNIVERSE_LIMIT)
    if not universe:
        return FALLBACK_WATCHLIST, False  # (종목코드 리스트, 동적유니버스사용여부)
    return universe[:limit], True


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/health")
def health():
    return jsonify({
        "ok": True,
        "kis_key_configured": config_store.has_kis_keys(),
        "missing_env_vars": config_store.missing_kis_env_vars(),
    })


@app.route("/api/market-signal")
def market_signal():
    data = kis_client.get_market_overview()
    if data is None:
        return jsonify({"error": "판단불가", "reason": "KIS 지수/수급 데이터 조회 실패 또는 키 미설정"}), 200
    return jsonify(data)


@app.route("/api/market-news")
def market_news():
    """시황 뉴스 — 네이버 금융 증시 메인뉴스 크롤링 (API 키 불필요). 실패 시 판단불가."""
    items = market_data_crawler.fetch_market_news()
    if items is None:
        return jsonify({"error": "판단불가", "reason": "뉴스 페이지 크롤링 실패(네트워크 또는 페이지 구조 변경)"}), 200
    return jsonify({"items": items})


@app.route("/api/stock-news/<code>")
def stock_news(code):
    """종목별 뉴스 — 네이버 금융 개별 종목 뉴스탭 크롤링 (API 키 불필요). 실패 시 판단불가."""
    items = market_data_crawler.fetch_stock_news(code)
    if items is None:
        return jsonify({"error": "판단불가", "reason": "뉴스 페이지 크롤링 실패(네트워크 또는 페이지 구조 변경)"}), 200
    return jsonify({"items": items})


@app.route("/api/sector-rankings")
def sector_rankings():
    """업종(섹터)별 실시간 등락률 — 네이버 금융 업종별시세 크롤링 (API 키 불필요). 실패 시 판단불가."""
    rows = market_data_crawler.fetch_sector_rankings()
    if rows is None:
        return jsonify({"error": "판단불가", "reason": "업종별시세 페이지 크롤링 실패(네트워크 또는 페이지 구조 변경)"}), 200
    return jsonify({"sectors": rows})


@app.route("/api/search-stock")
def search_stock():
    """검색창에 종목명을 입력했을 때 6자리 코드로 변환 (네이버 증권 자동완성, 인증 불필요)."""
    q = request.args.get("q", "").strip()
    matches = market_data_crawler.resolve_stock_code(q)
    if matches is None:
        return jsonify({"error": "판단불가", "reason": "종목 검색 API 조회 실패"}), 200
    return jsonify({"matches": matches})


@app.route("/api/stock/<code>")
def stock_detail(code):
    snap = kis_client.get_live_snapshot(code)
    if snap is None:
        return jsonify({"error": "판단불가", "reason": f"{code} 라이브 데이터 조회 실패"}), 200
    return jsonify(kis_client.snapshot_to_stock_item(snap))


@app.route("/api/case-scan", methods=["GET", "POST"])
def case_scan():
    """거래대금·등락률 상위 유니버스(최대 UNIVERSE_LIMIT종목) 중 상위 SCAN_LIMIT종목을
    CASE 1~11로 평가하고, 우선순위 규칙대로 TOP5를 반환"""
    watchlist, dynamic = get_watchlist()
    verdicts_by_case = {cid: [] for cid in CASE_PRIORITY_ORDER}
    errors = []
    for code in watchlist:
        snap = kis_client.get_live_snapshot(code)
        time.sleep(_CALL_DELAY_SEC)
        if snap is None:
            errors.append(code)
            continue
        for cid in CASE_PRIORITY_ORDER:
            verdicts_by_case[cid].append(evaluate_case(cid, snap))
    top5 = rank_top5(verdicts_by_case)
    return jsonify({
        "top5": [v.__dict__ for v in top5],
        "skipped_codes": errors,
        "universe_size": len(watchlist),
        "dynamic_universe": dynamic,  # False면 순위API 실패로 고정 5종목만 스캔된 상태
    })


@app.route("/api/closing-bet", methods=["GET", "POST"])
def closing_bet_scan():
    """거래대금·등락률 상위 유니버스 중 상위 SCAN_LIMIT종목에 대해
    종가배팅 5조건+8품질검증을 평가하고 상위 N개를 반환"""
    watchlist, dynamic = get_watchlist()
    volume_rows = kis_client.get_volume_rank_raw(UNIVERSE_LIMIT) or []
    fluct_rows = kis_client.get_fluctuation_rank_raw(UNIVERSE_LIMIT) or []
    trading_value_top_codes = {r.get("mksc_shrn_iscd") for r in volume_rows[:20]}
    change_rate_top_codes = {r.get("mksc_shrn_iscd") or r.get("stck_shrn_iscd") for r in fluct_rows[:10]}

    candidates = []
    errors = []
    for code in watchlist:
        snap = kis_client.get_live_snapshot(code)
        time.sleep(_CALL_DELAY_SEC)
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
        "universe_size": len(watchlist),
        "dynamic_universe": dynamic,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
