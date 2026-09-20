# -*- coding: utf-8 -*-
"""
kis_client.py
=============
한국투자증권(KIS) Open API 실전투자 클라이언트.

검증된 스펙 (공식/커뮤니티 문서 교차 확인 완료)
--------------------------------------------------------
- 접근토큰 발급   : POST /oauth2/tokenP  (grant_type=client_credentials)
- 주식현재가 시세 : GET  /uapi/domestic-stock/v1/quotations/inquire-price
                    tr_id = FHKST01010100
- 국내주식 기간별시세(일봉) : GET /uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice
                    tr_id = FHKST03010100
- 공통 헤더: authorization(Bearer), appkey, appsecret, tr_id, custtype(P=개인)
※ 투자자매매동향/지수 API는 TR_ID를 배포 전 apiportal.koreainvestment.com에서
  한 번 더 대조하는 것을 권장합니다 (아래 TODO 표시).

절대 원칙
---------
- 이 파일은 실제 데이터가 없으면 None을 반환한다. 임의의 숫자를 만들어내지 않는다.
- APP_KEY / APP_SECRET / 계좌정보는 config_store.py를 통해서만 읽는다 (하드코딩 금지).
"""

import time
import requests
from typing import Optional, List, Dict, Any

import config_store
from case_engine import LiveSnapshot

REAL_DOMAIN = "https://openapi.koreainvestment.com:9443"        # 실전투자
VIRTUAL_DOMAIN = "https://openapivts.koreainvestment.com:29443"  # 모의투자

_token_cache = {"access_token": None, "expires_at": 0}


def _base_url() -> str:
    return REAL_DOMAIN if config_store.get_kis_mode() == "prod" else VIRTUAL_DOMAIN


def _get_access_token() -> Optional[str]:
    """접근토큰 발급 (유효기간 1일, 캐싱해서 재사용). 키 미설정 시 None."""
    app_key, app_secret = config_store.get_kis_keys()
    if not app_key or not app_secret:
        return None

    if _token_cache["access_token"] and _token_cache["expires_at"] > time.time():
        return _token_cache["access_token"]

    try:
        res = requests.post(
            f"{_base_url()}/oauth2/tokenP",
            json={"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret},
            timeout=5,
        )
        res.raise_for_status()
        body = res.json()
        _token_cache["access_token"] = body["access_token"]
        _token_cache["expires_at"] = time.time() + int(body.get("expires_in", 86400)) - 60
        return _token_cache["access_token"]
    except requests.RequestException:
        return None


def _headers(tr_id: str) -> Optional[Dict[str, str]]:
    token = _get_access_token()
    app_key, app_secret = config_store.get_kis_keys()
    if not token:
        return None
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": tr_id,
        "custtype": "P",  # 개인
    }


def get_current_price_raw(code: str) -> Optional[Dict[str, Any]]:
    """주식현재가 시세 조회 (FHKST01010100)"""
    headers = _headers("FHKST01010100")
    if headers is None:
        return None
    try:
        res = requests.get(
            f"{_base_url()}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=headers,
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
            timeout=5,
        )
        res.raise_for_status()
        body = res.json()
        if body.get("rt_cd") != "0":
            return None
        return body.get("output")
    except requests.RequestException:
        return None


def get_daily_prices_raw(code: str, start_date: str = "00000101", end_date: str = "99991231",
                          period: str = "D") -> Optional[List[Dict[str, Any]]]:
    """국내주식 기간별시세 - 일봉 조회 (FHKST03010100). 한 번 호출에 최근 100건까지(공식 제약)."""
    headers = _headers("FHKST03010100")
    if headers is None:
        return None
    try:
        res = requests.get(
            f"{_base_url()}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            headers=headers,
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": start_date,
                "FID_INPUT_DATE_2": end_date,
                "FID_PERIOD_DIV_CODE": period,
                "FID_ORG_ADJ_PRC": "1",
            },
            timeout=5,
        )
        res.raise_for_status()
        body = res.json()
        if body.get("rt_cd") != "0":
            return None
        return body.get("output2")  # output1=종목요약, output2=일자별 배열(최근순)
    except requests.RequestException:
        return None


def get_investor_trend_raw(code: str) -> Optional[List[Dict[str, Any]]]:
    """종목별 투자자 매매동향(외국인/기관 수급) — ⚠️ TR_ID를 apiportal 문서에서 최신값 확인 후 구현"""
    # TODO: 배포 전 공식문서 대조 필요 (계좌 종류별 TR_ID가 다를 수 있음)
    return None


# ---------------------------------------------------------------------------
# 순위분석 API (거래대금/거래량 상위, 등락률 상위) — 감시 리스트를 5종목 고정에서
# "상위 N종목"으로 동적으로 넓히기 위해 사용. 커뮤니티 버그리포트로 교차 검증된 스펙.
# ⚠️ 외국인/기관 "수급" 자체의 순위 API(TR_ID)는 아직 미검증 — 지금은 거래대금+등락률
#    상위만으로 감시 유니버스를 구성한다 (TODO: 수급 상위 API 확인 후 추가).
# ---------------------------------------------------------------------------
_name_cache: Dict[str, str] = {}  # {종목코드: 종목명} - 순위 API 응답에서 채워짐, 현재가 조회 시 이름 누락되면 여기서 보완


def get_volume_rank_raw(count: int = 50) -> Optional[List[Dict[str, Any]]]:
    """거래량(거래대금) 순위 (FHPST01710000)"""
    headers = _headers("FHPST01710000")
    if headers is None:
        return None
    try:
        res = requests.get(
            f"{_base_url()}/uapi/domestic-stock/v1/quotations/volume-rank",
            headers=headers,
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_COND_SCR_DIV_CODE": "20171",
                "FID_INPUT_ISCD": "0000",       # 0000=전체
                "FID_DIV_CLS_CODE": "0",
                "FID_BLNG_CLS_CODE": "0",        # 거래량순
                "FID_TRGT_CLS_CODE": "111111111",
                "FID_TRGT_EXLS_CLS_CODE": "0000000000",
                "FID_INPUT_PRICE_1": "0",
                "FID_INPUT_PRICE_2": "0",
                "FID_VOL_CNT": "0",
                "FID_INPUT_DATE_1": "",
            },
            timeout=6,
        )
        res.raise_for_status()
        body = res.json()
        if body.get("rt_cd") != "0":
            return None
        rows = body.get("output", [])[:count]
        for r in rows:
            code, name = r.get("mksc_shrn_iscd"), r.get("hts_kor_isnm")
            if code and name:
                _name_cache[code] = name
        return rows
    except requests.RequestException:
        return None


def get_fluctuation_rank_raw(count: int = 50) -> Optional[List[Dict[str, Any]]]:
    """등락률 순위 (FHPST01700000)"""
    headers = _headers("FHPST01700000")
    if headers is None:
        return None
    try:
        res = requests.get(
            f"{_base_url()}/uapi/domestic-stock/v1/ranking/fluctuation",
            headers=headers,
            params={
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code": "20170",
                "fid_input_iscd": "0000",
                "fid_rank_sort_cls_code": "0",   # 0=상승률순
                "fid_input_cnt_1": str(count),
                "fid_prc_cls_code": "0",
                "fid_input_price_1": "0",
                "fid_input_price_2": "0",
                "fid_vol_cnt": "0",
                "fid_trgt_cls_code": "0",
                "fid_trgt_exls_cls_code": "0",
                "fid_div_cls_code": "0",
                "fid_rsfl_rate1": "0",
                "fid_rsfl_rate2": "0",
            },
            timeout=6,
        )
        res.raise_for_status()
        body = res.json()
        if body.get("rt_cd") != "0":
            return None
        rows = body.get("output", [])[:count]
        for r in rows:
            code, name = r.get("mksc_shrn_iscd") or r.get("stck_shrn_iscd"), r.get("hts_kor_isnm")
            if code and name:
                _name_cache[code] = name
        return rows
    except requests.RequestException:
        return None


def get_scan_universe(limit: int = 100) -> List[str]:
    """거래대금 상위 + 등락률 상위를 합쳐 감시 유니버스(종목코드 리스트)를 구성.
    순위 API가 실패하면 빈 리스트 반환(호출 측에서 정적 WATCHLIST로 대체 처리)."""
    codes: List[str] = []
    seen = set()
    for rows in (get_volume_rank_raw(limit), get_fluctuation_rank_raw(limit)):
        if not rows:
            continue
        for r in rows:
            code = r.get("mksc_shrn_iscd") or r.get("stck_shrn_iscd")
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
            if len(codes) >= limit:
                break
        if len(codes) >= limit:
            break
    return codes[:limit]


def lookup_cached_name(code: str) -> Optional[str]:
    """순위 API 조회 중 확보한 종목명 캐시. 현재가 API가 이름을 안 줄 때 보완용."""
    return _name_cache.get(code)


def get_live_snapshot(code: str) -> Optional["LiveSnapshot"]:
    """case_engine.LiveSnapshot 형태로 조립. 조회 실패 필드는 None으로 남겨
    case_engine/closing_bet이 스스로 '판단불가' 처리하도록 한다 (임의로 채우지 않음)."""
    price_raw = get_current_price_raw(code)
    if price_raw is None:
        return None
    daily_raw = get_daily_prices_raw(code)
    investor_raw = get_investor_trend_raw(code)

    def _f(key, default=None):
        v = price_raw.get(key)
        try:
            return float(v) if v not in (None, "") else default
        except (TypeError, ValueError):
            return default

    ma5 = ma10 = ma20 = ma60 = ma120 = None
    high_20d = low_20d = high_60d = low_60d = None
    if daily_raw:
        closes = [float(r["stck_clpr"]) for r in daily_raw if r.get("stck_clpr")]
        highs = [float(r["stck_hgpr"]) for r in daily_raw if r.get("stck_hgpr")]
        lows = [float(r["stck_lwpr"]) for r in daily_raw if r.get("stck_lwpr")]

        def _avg(vals, n):
            return round(sum(vals[:n]) / n, 2) if len(vals) >= n else None
        ma5, ma10, ma20 = _avg(closes, 5), _avg(closes, 10), _avg(closes, 20)
        ma60, ma120 = _avg(closes, 60), _avg(closes, 120)
        if len(highs) >= 20: high_20d = max(highs[:20])
        if len(lows) >= 20: low_20d = min(lows[:20])
        if len(highs) >= 60: high_60d = max(highs[:60])
        if len(lows) >= 60: low_60d = min(lows[:60])

    return LiveSnapshot(
        stock_code=code,
        stock_name=price_raw.get("hts_kor_isnm") or _name_cache.get(code),
        current_price=_f("stck_prpr"),
        prev_close=_f("stck_sdpr"),
        open_price=_f("stck_oprc"),
        high_price=_f("stck_hgpr"),
        low_price=_f("stck_lwpr"),
        volume=_f("acml_vol"),
        change_rate_pct=_f("prdy_ctrt"),
        trading_value_today=_f("acml_tr_pbmn"),
        ma5=ma5, ma10=ma10, ma20=ma20, ma60=ma60, ma120=ma120,
        high_20d=high_20d, low_20d=low_20d, high_60d=high_60d, low_60d=low_60d,
        daily_prices=daily_raw,
        investor_rows=investor_raw,
        raw_source_ts=str(int(time.time())),
        # foreign_net_buy_*, inst_net_buy_*, pension_net_buy_cum20 등은
        # investor_rows(투자자매매동향 API 구현 후) 기반으로 채워야 함 — 현재는 None 유지
    )


def snapshot_to_stock_item(snap: "LiveSnapshot") -> Dict[str, Any]:
    """프런트엔드 StockItem 스키마로 변환 (RS/MTT/재무추정은 별도 계산 로직 필요 — TODO)"""
    return {
        "code": snap.stock_code,
        "name": snap.stock_name,
        "price": snap.current_price,
        "changeRate": snap.change_rate_pct,
        "volumeValue": snap.trading_value_today,
        "ma5": snap.ma5, "ma20": snap.ma20, "ma60": snap.ma60,
        "resistance": snap.high_20d, "support": snap.low_20d,
        "dailyPrices": snap.daily_prices,
    }


def get_market_overview() -> Optional[Dict[str, Any]]:
    """지수/수급 개요 — TODO: 코스피/코스닥 지수 + 투자자별 매매동향 API 연결"""
    if _get_access_token() is None:
        return None
    return None  # TODO: 구현


def get_top_rank_code_sets(codes: List[str]):
    """감시 리스트 내에서 거래대금 상위/등락률 상위 종목 코드 집합을 근사 산출.
    실전 연동 시 KIS 순위 조회 API로 교체 권장."""
    prices = {c: get_current_price_raw(c) for c in codes}
    valid = {c: p for c, p in prices.items() if p}
    by_value = sorted(valid.items(), key=lambda kv: float(kv[1].get("acml_tr_pbmn", 0) or 0), reverse=True)
    by_rate = sorted(valid.items(), key=lambda kv: float(kv[1].get("prdy_ctrt", 0) or 0), reverse=True)
    return {c for c, _ in by_value[:20]}, {c for c, _ in by_rate[:10]}
