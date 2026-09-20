# -*- coding: utf-8 -*-
"""
closing_bet.py
===============
사용자가 제시한 '종가배팅 후보주' 5가지 선정 조건 + 8가지 추가 품질 검증을 구현한 모듈.

절대 원칙 (case_engine.py와 동일)
---------------------------------
1. 실제로 조회된 라이브 데이터로만 판정한다. 데이터가 없으면 "판단불가"로 명시하고
   숫자나 뉴스 내용을 지어내지 않는다.
2. 아래 항목들은 이 앱에 연동된 KIS Open API만으로는 신뢰성 있게 확인할 수 없어서,
   항상(또는 관련 API 키 미설정 시) "판단불가"로 표시한다 - 거짓으로 '확인됨'이라고
   표시하지 않는다:
     - 뉴스가 실제로 "정책펀드/빅파마 계약 완료 수준"인지 여부 (기사 존재 여부까지는
       네이버 뉴스 검색 API로 확인 가능하지만, 내용의 질적 판단은 사람이 직접 읽어야 함)
     - 공매도 비중/대주주 매도 공시 (별도 데이터소스: 공매도 종합포털, DART 전자공시 -
       이 앱에는 연동되어 있지 않음)
     - 실시간(장중 15시 직전) 1분/5분봉 매수잔량 우위 (실시간 호가/분봉 스트림 미연동 -
       이 앱은 일봉 데이터까지만 사용)
     - "매수 체결강도" (실시간 체결 데이터 필요, 미연동)
3. '테마 대장주'는 KIS Open API에 표준화된 테마 분류가 없어, 등락률 상위 종목으로
   근사한다 - 실제 HTS의 테마 그룹과 다를 수 있음을 항상 함께 표시한다.
4. '장초반 급등 후 횡보'는 분봉 데이터 없이 일봉의 당일 고가 대비 현재가로만 근사한다 -
   진짜 09~10시 vs 15시 시간대별 패턴이 아님을 항상 함께 표시한다.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from case_engine import LiveSnapshot, compute_rsi, compute_atr, count_consecutive_net_buy_days
import news_client
import dart_client
import market_context
import config_store

TRADING_VALUE_TOP_N = 20   # 조건1: 거래대금 상위 N
CHANGE_RATE_TOP_N = 10      # 조건2: 등락률 상위 N (테마 대장주 근사)
MIN_SUPPLY_AMOUNT_WON = 5_000_000_000  # 조건/품질체크3: 순매수금액 50억 기준

CONDITION_LABELS = ["거래대금", "테마 대장주(근사)", "외국인/기관 수급", "장초반 급등후 횡보(근사)", "뉴스 모멘텀"]
QUALITY_LABELS = [
    "1. 거래량 질(5~10일 평균비 3~5배)",
    "2. 기술적 위치(고가-3%+이평+RSI)",
    "3. 수급의 질(동반매수+금액기준)",
    "4. 뉴스 지속성 필터",
    "5. 섹터/시장 컨텍스트",
    "6. 공매도/대주주 리스크",
    "7. 실시간 마이크로 패턴",
    "8. 리스크 관리(ATR 손절/포지션)",
]


@dataclass
class CheckItem:
    label: str
    status: str   # "✅" | "❌" | "판단불가"
    detail: str
    news_items: Optional[List[Dict[str, Any]]] = None


@dataclass
class ClosingBetCandidate:
    stock_code: str
    stock_name: Optional[str]
    current_price: Optional[float]
    change_rate_pct: Optional[float]
    reason_summary: str
    conditions: List[CheckItem]       # 5가지 선정 조건
    quality_checks: List[CheckItem]   # 8가지 추가 품질 검증
    target_price: Optional[float]
    target_basis: str
    stop_loss: Optional[float]
    stop_loss_basis: str
    risk_notes: List[str]
    match_score: int   # 5가지 조건 중 ✅ 개수 (정렬용)


def _fmt_pct(v: Optional[float]) -> str:
    return f"{v:+.2f}%" if v is not None else "미확보"


def _fmt_won(v: Optional[float]) -> str:
    return f"{v:,.0f}원" if v is not None else "미확보"


def evaluate_closing_bet_candidate(
    snap: LiveSnapshot,
    is_trading_value_top: bool,
    is_change_rate_top: bool,
) -> ClosingBetCandidate:
    conditions: List[CheckItem] = []
    quality: List[CheckItem] = []

    # ---- 조건 1: 거래대금 상위 (급증 + 상승 조합) ----
    if snap.trading_value_today is None or snap.change_rate_pct is None:
        conditions.append(CheckItem(CONDITION_LABELS[0], "판단불가", "거래대금/등락률 데이터 미확보"))
    else:
        ok = is_trading_value_top and snap.change_rate_pct > 0
        est_note = " (근사치: 종가×거래량)" if snap.trading_value_is_estimated else " (실측)"
        conditions.append(CheckItem(
            CONDITION_LABELS[0], "✅" if ok else "❌",
            f"당일 거래대금 상위{TRADING_VALUE_TOP_N} {'포함' if is_trading_value_top else '미포함'}{est_note} · "
            f"등락률 {_fmt_pct(snap.change_rate_pct)}",
        ))

    # ---- 조건 2: 테마 대장주 (등락률 상위 근사) ----
    if snap.change_rate_pct is None:
        conditions.append(CheckItem(CONDITION_LABELS[1], "판단불가", "등락률 데이터 미확보"))
    else:
        conditions.append(CheckItem(
            CONDITION_LABELS[1], "✅" if is_change_rate_top else "❌",
            f"당일 등락률 상위{CHANGE_RATE_TOP_N} {'포함' if is_change_rate_top else '미포함'} "
            "(KIS에 표준 테마 분류가 없어 등락률 순위로 근사 - 실제 HTS 테마 그룹과 다를 수 있음)",
        ))

    # ---- 조건 3: 외국인+기관 동반 순매수 ----
    consec = 0
    if snap.foreign_net_buy_1d is None or snap.inst_net_buy_1d is None:
        conditions.append(CheckItem(CONDITION_LABELS[2], "판단불가", "수급 데이터 미확보"))
    else:
        consec = count_consecutive_net_buy_days(snap.investor_rows, "frgn_ntby_qty") if snap.investor_rows else 0
        ok = snap.foreign_net_buy_1d > 0 and snap.inst_net_buy_1d > 0
        conditions.append(CheckItem(
            CONDITION_LABELS[2], "✅" if ok else "❌",
            f"외국인 순매수 {snap.foreign_net_buy_1d:,.0f} / 기관 순매수 {snap.inst_net_buy_1d:,.0f} "
            f"(외국인 연속매수 {consec}일)",
        ))

    # ---- 조건 4: 장초반 급등 후 횡보 (일봉 기준 근사) ----
    pullback_pct = None
    if snap.high_price is None or snap.current_price is None or snap.high_price == 0:
        conditions.append(CheckItem(CONDITION_LABELS[3], "판단불가", "당일 고가/현재가 데이터 미확보"))
    else:
        pullback_pct = (snap.high_price - snap.current_price) / snap.high_price * 100
        ok = 0 <= pullback_pct <= 3
        conditions.append(CheckItem(
            CONDITION_LABELS[3], "✅" if ok else "❌",
            f"당일 고가 대비 {pullback_pct:.1f}% (일봉 기준 근사치 - 실제 09~10시 급등 여부는 "
            "분봉 데이터 미연동으로 이 앱에서 자동 확인 불가, 직접 차트 확인 권장)",
        ))

    # ---- 조건 5: 뉴스 모멘텀 (네이버 뉴스 + DART 공식 공시 결합) ----
    news_items = news_client.search_recent_news(snap.stock_name) if snap.stock_name else None
    dart_key = config_store.get_dart_api_key()
    dart_items = dart_client.search_recent_disclosures(snap.stock_code, dart_key, days=14) if dart_key else []
    if news_items is None and not dart_key:
        conditions.append(CheckItem(CONDITION_LABELS[4], "판단불가",
                                     "뉴스/공시 API 미연동 - 수동 확인 필요 (NAVER_CLIENT_ID/SECRET, DART_API_KEY 환경변수 설정 시 활성화)"))
    elif (news_items is None or len(news_items) == 0) and len(dart_items) == 0:
        conditions.append(CheckItem(CONDITION_LABELS[4], "❌", "관련 최근 뉴스/공시 검색 결과 없음"))
    else:
        parts = []
        if news_items:
            parts.append(f"네이버 뉴스 {len(news_items)}건")
        if dart_items:
            parts.append(f"DART 공시 {len(dart_items)}건(공식·고신뢰)")
        conditions.append(CheckItem(
            CONDITION_LABELS[4], "✅",
            f"{' / '.join(parts)} 검색됨 - 아래 링크/공시에서 직접 내용 확인 필요 "
            "(정책펀드/빅파마 계약 등 펀더멘털 뉴스인지는 자동 판단하지 않음)",
            news_items=news_items,
        ))

    # 거래대금·등락률(조건1) 충족은 다른 조건보다 신뢰도가 높은 '실측' 데이터이므로
    # match_score에서 2배로 가중한다(최대 5→최대 7점). 동점 시 등락률로 2차 정렬한다.
    match_score = 0
    for i, c in enumerate(conditions):
        if c.status != "✅":
            continue
        match_score += 2 if i == 0 else 1

    # ---- 품질 검증 1~8 ----
    rsi = compute_rsi(snap.daily_prices) if snap.daily_prices else None
    atr = compute_atr(snap.daily_prices) if snap.daily_prices else None

    # 1) 거래량 질
    vol_ratio = None
    if snap.volume is not None and snap.avg_trading_value_5d and snap.avg_trading_value_5d > 0 and snap.current_price:
        avg_volume_5d_approx = snap.avg_trading_value_5d / snap.current_price if snap.current_price else None
        if avg_volume_5d_approx and avg_volume_5d_approx > 0:
            vol_ratio = snap.volume / avg_volume_5d_approx
    if vol_ratio is None:
        quality.append(CheckItem(QUALITY_LABELS[0], "판단불가", "평균 거래량 대비 비율 산출 불가 (데이터 부족)"))
    else:
        ok = vol_ratio >= 3
        quality.append(CheckItem(QUALITY_LABELS[0], "✅" if ok else "❌",
                                  f"최근 평균 대비 거래량 약 {vol_ratio:.1f}배 (근사치) · 매수체결강도는 실시간 체결 데이터 미연동으로 판단불가"))

    # 2) 기술적 위치
    if pullback_pct is None or snap.ma5 is None or snap.ma20 is None or snap.current_price is None:
        quality.append(CheckItem(QUALITY_LABELS[1], "판단불가", "고가/이평선 데이터 일부 미확보"))
    else:
        above_ma = snap.current_price > snap.ma5 and snap.current_price > snap.ma20
        rsi_ok = rsi is not None and 55 <= rsi <= 75
        ok = (0 <= pullback_pct <= 3) and above_ma and rsi_ok
        rsi_text = f"{rsi}" if rsi is not None else "판단불가"
        quality.append(CheckItem(QUALITY_LABELS[1], "✅" if ok else "❌",
                                  f"고가대비 {pullback_pct:.1f}% · 5일/20일선 상회 {'예' if above_ma else '아니오'} · RSI {rsi_text}"))

    # 3) 수급의 질 (금액 기준 - 금액 필드가 없으면 수량 기준으로만 판단하고 명시)
    if snap.foreign_net_buy_amount_1d is not None or snap.inst_net_buy_amount_1d is not None:
        amt = (snap.foreign_net_buy_amount_1d or 0) + (snap.inst_net_buy_amount_1d or 0)
        ok = amt >= MIN_SUPPLY_AMOUNT_WON
        quality.append(CheckItem(QUALITY_LABELS[2], "✅" if ok else "❌",
                                  f"외국인+기관 순매수 합산 약 {_fmt_won(amt)} (50억원 기준) · 연기금/프로그램 세부 구분은 판단불가"))
    elif snap.foreign_net_buy_1d is not None and snap.inst_net_buy_1d is not None:
        ok = snap.foreign_net_buy_1d > 0 and snap.inst_net_buy_1d > 0
        quality.append(CheckItem(QUALITY_LABELS[2], "✅" if ok else "❌",
                                  "동반 순매수 수량 기준으로만 확인됨(금액 필드 미확보 - 50억원 기준 금액 판정은 불가) · "
                                  "연기금/프로그램 세부 구분은 판단불가"))
    else:
        quality.append(CheckItem(QUALITY_LABELS[2], "판단불가", "수급 데이터 미확보"))

    # 4) 뉴스 지속성 필터 (조건5와 동일 데이터 재사용 - 중복 API 호출 방지)
    if news_items is None:
        quality.append(CheckItem(QUALITY_LABELS[3], "판단불가", "뉴스 API 미연동 - 수동 확인 필요"))
    else:
        quality.append(CheckItem(QUALITY_LABELS[3], "판단불가" if len(news_items) == 0 else "❓ 수동 확인 필요",
                                  f"뉴스 {len(news_items)}건 검색됨 - 단발성 테마인지 정책펀드/빅파마 계약 수준인지는 "
                                  "직접 읽고 판단해야 함(자동 판단 안 함)"))

    # 5) 섹터/시장 컨텍스트 (FinanceDataReader로 KOSDAQ 지수 실측 등락률 조회)
    kq_up = market_context.kosdaq_is_up()
    if kq_up is None:
        quality.append(CheckItem(QUALITY_LABELS[4], "판단불가",
                                  "KOSDAQ 지수 조회 실패 - 해당 테마가 시장 주도 테마인지 여부는 여전히 판단불가"))
    else:
        quality.append(CheckItem(QUALITY_LABELS[4], "✅" if kq_up else "❌",
                                  f"오늘 KOSDAQ 지수 {'상승' if kq_up else '하락/보합'} 중(실측) - "
                                  "해당 종목의 테마가 시장을 주도하는 테마인지 여부까지는 판단불가"))

    # 6) 공매도/대주주 리스크 (DART 대주주 지분변동 공시만 실측 반영, 공매도 비중은 여전히 판단불가)
    confirmed, dart_disc_items = dart_client.has_recent_major_shareholder_disclosure(
        snap.stock_code, dart_key, days=14
    )
    if confirmed is None:
        quality.append(CheckItem(QUALITY_LABELS[5], "판단불가",
                                  "DART_API_KEY 미설정 또는 조회 실패로 대주주 지분변동 공시 확인 불가 · "
                                  "공매도 비중은 별도 데이터소스(공매도 종합포털) 필요 - 매매 전 수동 확인 권장"))
    elif len(dart_disc_items) > 0:
        quality.append(CheckItem(QUALITY_LABELS[5], "❌",
                                  f"최근 14일 내 DART 대주주 지분변동 공시 {len(dart_disc_items)}건 발견(공식) - "
                                  "매도 공시인지 직접 확인 필요 · 공매도 비중은 여전히 판단불가"))
    else:
        quality.append(CheckItem(QUALITY_LABELS[5], "✅",
                                  "최근 14일 내 DART 대주주 지분변동 공시 없음(공식 확인) · "
                                  "공매도 비중은 별도 데이터소스 필요로 여전히 판단불가"))

    # 7) 실시간 마이크로 패턴
    quality.append(CheckItem(QUALITY_LABELS[6], "판단불가",
                              "실시간 1분/5분봉·호가 잔량 데이터는 미연동(이 앱은 일봉 기준까지만 사용) - "
                              "매수 직전 HTS/MTS 차트에서 직접 확인 필요"))

    # 8) 리스크 관리(ATR 손절/포지션)
    if atr is not None and snap.current_price is not None:
        stop_loss = round(snap.current_price - atr * 1.5, 0)
        stop_basis = f"ATR(14)={atr:,.1f} 기준: 현재가 − ATR×1.5"
        quality.append(CheckItem(QUALITY_LABELS[7], "✅",
                                  f"ATR 기반 손절가 {stop_loss:,.0f}원 제안 · 개별 종목 매수금액은 총 투자금의 1~2% 이내로 "
                                  "제한 권장 · 목표가 도달 시 50% 이상 분할 익절 권장(자동 매도 아님, 수동 실행 필요)"))
    else:
        stop_loss = round(snap.current_price * 0.97, 0) if snap.current_price else None
        stop_basis = "ATR 계산 불가(데이터 부족)로 -3% 근사치 사용"
        quality.append(CheckItem(QUALITY_LABELS[7], "판단불가" if atr is None else "✅",
                                  "ATR 계산에 필요한 일봉 데이터 부족 - 근사치(-3%)로 대체 · 개별 종목 매수금액은 "
                                  "총 투자금의 1~2% 이내로 제한 권장"))

    target_price = None
    target_basis = "데이터 부족으로 산출 불가"
    if snap.high_20d is not None:
        target_price = round(snap.high_20d * 1.05, 0)
        target_basis = f"최근 20일 고가 {snap.high_20d:,.0f}원 재돌파 기준 +5% 근사 목표"
    elif snap.current_price is not None:
        target_price = round(snap.current_price * 1.05, 0)
        target_basis = "최근 고가 데이터 미확보로 현재가 +5% 근사 목표 사용"

    reason_parts = []
    for c in conditions:
        if c.status == "✅":
            reason_parts.append(c.label)
    reason_summary = ("충족: " + ", ".join(reason_parts)) if reason_parts else "충족된 핵심 조건 없음(참고용으로만 확인)"

    risk_notes = [
        "목표가/손절가는 규칙 기반 근사치이며 확정된 미래 예측이 아닙니다.",
        "뉴스/공매도/실시간 호가 관련 항목은 이 앱에 자동 연동되어 있지 않은 경우 반드시 직접 확인 후 매매하세요.",
        "포지션 크기는 총 투자금의 1~2% 이내로 제한하고, 목표가 도달 시 최소 50%는 분할 익절하는 것을 권장합니다(자동 실행 아님).",
    ]

    return ClosingBetCandidate(
        stock_code=snap.stock_code,
        stock_name=snap.stock_name,
        current_price=snap.current_price,
        change_rate_pct=snap.change_rate_pct,
        reason_summary=reason_summary,
        conditions=conditions,
        quality_checks=quality,
        target_price=target_price,
        target_basis=target_basis,
        stop_loss=stop_loss,
        stop_loss_basis=stop_basis,
        risk_notes=risk_notes,
        match_score=match_score,
    )


def rank_closing_bet_candidates(candidates: List[ClosingBetCandidate], top_n: int = 10) -> List[ClosingBetCandidate]:
    """match_score(거래대금 조건 2배 가중 포함, 최대 7점) 내림차순 정렬. 동점이면 당일
    등락률이 높은 종목을 우선한다(순위 흔들림 완화)."""
    return sorted(
        candidates,
        key=lambda c: (c.match_score, c.change_rate_pct if c.change_rate_pct is not None else -999),
        reverse=True,
    )[:top_n]
