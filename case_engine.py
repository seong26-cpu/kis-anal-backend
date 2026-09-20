# -*- coding: utf-8 -*-
"""
case_engine.py
==============
'세력추적_조건검색식_가이드.jsx'에 정의된 CASE 1~11의 개념을 그대로 규칙으로 옮긴 모듈입니다.

절대 원칙 (사용자 요청 반영)
---------------------------
1. 이 모듈은 어떤 종목명/가격/수급 데이터도 스스로 만들어내지 않습니다.
   모든 계산은 kis_client.py 를 통해 실제로 조회된 라이브 데이터(dict)를 입력받아서만 수행됩니다.
2. 라이브 데이터가 없거나 부족하면 반드시 "판단 불가"를 반환하고, 절대 임의의 숫자로 채우지 않습니다.
3. CASE 우선순위는 사용자가 지정한 확률 순위를 그대로 따릅니다:
   9 -> 8 -> 1 -> 2 -> 10 -> 11 -> 5 -> 6 -> 7 -> 3 -> 4
4. 목표가/이탈가 산출식은 가이드에 서술된 '개념'을 규칙으로 근사한 것이며 100% 확정된 진실이 아닙니다.
   (예: "박스권 상단 돌파" -> 목표가 = 박스권 상단 + 박스 높이 등)
   실제 매매 전 반드시 본인 검증을 거쳐야 하며, 이 사실을 API 응답에도 명시합니다.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


# ---------------------------------------------------------------------------
# 1) 사용자가 지정한 CASE 우선순위 (확률 높은 순)
# ---------------------------------------------------------------------------
CASE_PRIORITY_ORDER: List[int] = [9, 8, 1, 2, 10, 11, 5, 6, 7, 3, 4]

# 우선순위 -> 등급 라벨 (가이드/대화에서 사용자가 명시한 확률 등급)
CASE_PROBABILITY_LABEL: Dict[int, str] = {
    9: "최고 확률",
    8: "매우 높음",
    1: "높음",
    2: "높음",
    10: "중상",
    11: "중상",
    5: "중",
    6: "중",
    7: "중하",
    3: "중하",
    4: "상대적 낮음",
}

# 케이스별 매수 판단 성격: "즉시형"(장중 즉시 확인) / "종가확인형"(종가 확정 후 신뢰도 상승) / "스윙형"(중기 스크리닝)
CASE_TIMING_STYLE: Dict[int, str] = {
    1: "종가확인형",
    2: "종가확인형",
    3: "즉시형",
    4: "종가확인형",
    5: "즉시형",
    6: "즉시형",
    7: "종가확인형",
    8: "스윙형",
    9: "스윙형",
    10: "종가확인형",
    11: "즉시형",
}

CASE_TITLES: Dict[int, str] = {
    1: "신고가 횡보 + 이평선 수렴 + 외국인 연속매수",
    2: "장기조정 후 20일선 돌파 + 기관 매집",
    3: "거래대금 급증 + 프로그램 매수 전환",
    4: "급락 후 아래꼬리 + 20일선 지지 (저가매수)",
    5: "과열 후 조정 + 매물대 돌파",
    6: "지수급락 속 지지 방어 + 기관매수",
    7: "급락 회복탄력 + 이평선밀집 반등",
    8: "변동성 속 정배열 우상향 + 연기금매집",
    9: "견고한 우상향 + 연기금 지속매집",
    10: "전고점 실패 후 저점상향 + 기관외인 동반매수",
    11: "박스권 돌파 시도 + 120일선 우상향",
}


@dataclass
class LiveSnapshot:
    """kis_client 가 실제로 조회해 채워야 하는 라이브 데이터. None 이면 '데이터 없음' 처리."""
    stock_code: str
    stock_name: Optional[str] = None
    current_price: Optional[float] = None
    prev_close: Optional[float] = None
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    volume: Optional[float] = None
    prev_volume: Optional[float] = None
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    ma120: Optional[float] = None
    high_20d: Optional[float] = None   # 최근 20거래일 고가
    low_20d: Optional[float] = None
    high_60d: Optional[float] = None   # 최근 60거래일 고가 (박스권 상단)
    low_60d: Optional[float] = None
    foreign_net_buy_1d: Optional[float] = None   # 전일 외국인 순매수 수량/금액
    foreign_net_buy_2d: Optional[float] = None   # 2일 연속 여부 판단용 (전전일)
    inst_net_buy_1d: Optional[float] = None
    inst_net_buy_cum20: Optional[float] = None   # 최근 20일 누적 기관 순매수
    pension_net_buy_cum20: Optional[float] = None  # 연기금 20일 누적 (세부 구분 미제공 시 None)
    program_net_buy_today: Optional[float] = None
    raw_source_ts: Optional[str] = None  # 데이터 조회 시각 (신뢰도 표기용)

    # ---- 종가배팅 후보 스캐너용 추가 필드 ----
    change_rate_pct: Optional[float] = None       # 전일대비 등락률(%) - KIS 응답값 실측
    trading_value_today: Optional[float] = None   # 당일 누적 거래대금(원) - KIS 응답값 실측, 없으면 종가*거래량으로 근사
    trading_value_is_estimated: bool = False       # 위 거래대금이 KIS 실측값이 아니라 근사치인 경우 True
    avg_trading_value_5d: Optional[float] = None   # 최근 5일 평균 거래대금(근사) - 등락률/거래대금 급증 판단용
    daily_prices: Optional[List[Dict[str, Any]]] = None  # RSI/ATR 계산 등에 재사용할 원본 일봉 리스트
    investor_rows: Optional[List[Dict[str, Any]]] = None  # 연속 순매수일수 계산에 재사용할 수급 원본 리스트
    foreign_net_buy_amount_1d: Optional[float] = None  # 전일 외국인 순매수 "금액"(원) - 필드 존재 시에만 채움
    inst_net_buy_amount_1d: Optional[float] = None     # 전일 기관 순매수 "금액"(원) - 필드 존재 시에만 채움


@dataclass
class CaseVerdict:
    case_id: int
    stock_code: str
    stock_name: Optional[str]
    verdict: str                 # "적극매수" | "매수" | "관망" | "판단불가"
    action_timing: str           # 예: "즉시", "1주일 관망 후 재확인", "종가 확정 후 익일 시가 확인"
    current_price: Optional[float]
    target_price: Optional[float]
    target_basis: str            # 목표가 산출 근거(사람이 읽는 설명)
    exit_price: Optional[float]  # 이탈가(관망/보유 중 이 가격 이탈 시 후보 교체)
    exit_basis: str
    supply_demand_note: str      # 외국인/기관/연기금 수급 상태 요약(실제 조회값 기반)
    reasons: List[str]           # 조건 충족 근거 목록 (전부 실측값 기반 문장)
    warnings: List[str]          # 데이터 미확보/근사치 경고
    prohibited_actions: List[str]
    data_confidence: str         # "실측" | "일부 미확보" | "판단불가(데이터 부족)"


COMMON_PROHIBITED_ACTIONS = [
    "이탈가(전략 무효화 가격)를 하회했는데도 '더 지켜보자'며 손절을 미루는 행위",
    "목표가 도달 전 뉴스/루머만으로 추가 물량을 몰아서 매수하는 행위(분할 매수 원칙 위반)",
    "장 마감 전 미확정 데이터(잠정 수급)만으로 '종가확인형' 케이스를 즉시 매매로 실행하는 행위",
    "동일 종목에 대해 서로 다른 CASE 근거를 섞어 손절 기준을 임의로 상향/하향하는 행위",
]


def _missing(*vals) -> bool:
    return any(v is None for v in vals)


def evaluate_case(case_id: int, snap: LiveSnapshot) -> CaseVerdict:
    """단일 종목 x 단일 CASE에 대해 실측 데이터만으로 판단을 계산한다.
    필요한 데이터가 없으면 verdict='판단불가' 로 명시하고 숫자를 지어내지 않는다."""

    reasons: List[str] = []
    warnings: List[str] = []
    verdict = "관망"
    timing_style = CASE_TIMING_STYLE.get(case_id, "종가확인형")

    def base_timing_text() -> str:
        if timing_style == "즉시형":
            return "즉시(장중 실시간 확인 필요)"
        if timing_style == "스윙형":
            return "스윙 관점 - 눌림목(단기 조정) 발생 시 분할 진입, 급하게 즉시 진입할 필요는 없음"
        return "당일 종가 확정 후 신뢰도 상승 - 종가 확인(14:30~15:20) 후 익일 시가로 최종 판단"

    action_timing = base_timing_text()
    target_price = None
    target_basis = "데이터 부족으로 산출 불가"
    exit_price = None
    exit_basis = "데이터 부족으로 산출 불가"
    supply_demand_note = "수급 데이터 미확보"

    # ---- 수급 요약 (실측값이 있는 것만 문장화) ----
    sd_parts = []
    if snap.foreign_net_buy_1d is not None:
        sd_parts.append(f"전일 외국인 순매수 {snap.foreign_net_buy_1d:,.0f}")
    if snap.inst_net_buy_1d is not None:
        sd_parts.append(f"전일 기관 순매수 {snap.inst_net_buy_1d:,.0f}")
    if snap.inst_net_buy_cum20 is not None:
        sd_parts.append(f"최근 20일 기관 누적순매수 {snap.inst_net_buy_cum20:,.0f}")
    if snap.pension_net_buy_cum20 is not None:
        sd_parts.append(f"최근 20일 연기금 누적순매수 {snap.pension_net_buy_cum20:,.0f}")
    if sd_parts:
        supply_demand_note = " / ".join(sd_parts)

    # ---- CASE 별 목표가/이탈가/조건 판단 ----
    if case_id == 1:
        # 신고가 횡보 + 이평선 수렴 + 외국인 연속매수
        if _missing(snap.current_price, snap.high_20d, snap.ma5, snap.ma20):
            warnings.append("현재가/최근20일고가/5·20일 이평선 중 일부 미확보")
        else:
            box_top = snap.high_20d
            target_price = round(box_top * 1.05, 0)  # 박스 상단 재돌파 + 통상 스윙 목표(5%) — 근사치
            target_basis = f"최근 20일 고가(박스권 상단) {box_top:,.0f}원 재돌파 기준 +5% 근사 목표"
            exit_price = round(snap.ma5, 0) if snap.ma5 else None
            exit_basis = "5일선 이탈 시 수렴 구도 붕괴로 판단, 후보 교체"
            if snap.current_price >= box_top:
                reasons.append(f"현재가 {snap.current_price:,.0f}원이 박스권 상단 {box_top:,.0f}원 이상 (돌파 진행)")
                if snap.foreign_net_buy_1d and snap.foreign_net_buy_1d > 0 and snap.foreign_net_buy_2d and snap.foreign_net_buy_2d > 0:
                    verdict = "적극매수"
                    action_timing = "즉시 (박스 상단 돌파 + 외국인 2일 연속 순매수 확인됨)"
                    reasons.append("외국인 2거래일 연속 순매수 확인")
                else:
                    verdict = "매수"
                    action_timing = "돌파는 확인되었으나 외국인 2일 연속 순매수 미확인 - 당일 종가 기준 재확인 후 진입"
            else:
                verdict = "관망"
                action_timing = "박스권 상단 재돌파 전 - 최대 1주일 관망 후 돌파 여부 재확인"
                reasons.append(f"현재가 {snap.current_price:,.0f}원, 박스권 상단 {box_top:,.0f}원 아직 미돌파")

    elif case_id == 2:
        if _missing(snap.current_price, snap.ma20, snap.volume, snap.prev_volume):
            warnings.append("현재가/20일선/거래량 데이터 일부 미확보")
        else:
            exit_price = round(snap.ma20, 0)
            exit_basis = "20일선(종가 기준) 재이탈 시 돌파 실패로 간주, 후보 교체"
            target_price = round(snap.ma20 * 1.10, 0) if snap.ma20 else None
            target_basis = "20일선 돌파 시작가 대비 통상 스윙 목표(+10%) 근사치"
            vol_ratio = (snap.volume / snap.prev_volume) if snap.prev_volume else None
            if snap.current_price > snap.ma20 and vol_ratio and vol_ratio >= 1.5:
                reasons.append(f"20일선 {snap.ma20:,.0f}원 상향 돌파, 거래량 전일比 {vol_ratio*100:.0f}%")
                if snap.inst_net_buy_cum20 and snap.inst_net_buy_cum20 > 0:
                    verdict = "적극매수"
                    action_timing = "종가 확정 확인 후 즉시(익일 시가 갭 여부로 2차 확인 권장)"
                    reasons.append("최근 20일 기관 누적 순매수 확인")
                else:
                    verdict = "매수"
                    action_timing = "돌파는 확인, 기관 누적 매수 데이터 미확인 - 신중 진입"
            else:
                verdict = "관망"
                action_timing = "20일선 돌파 미확정 - 종가 기준(15:20~15:30) 재확인 필요"

    elif case_id == 3:
        if _missing(snap.current_price, snap.low_price, snap.program_net_buy_today):
            warnings.append("현재가/저가/프로그램 순매수 데이터 미확보 (실시간 조건검색 병행 권장)")
        else:
            rise_from_low = (snap.current_price - snap.low_price) / snap.low_price if snap.low_price else 0
            target_price = round(snap.current_price * 1.05, 0)
            target_basis = "단기 반등 트리거 성격 - 진입가 대비 +5% 근사 목표(지속성 약함, 짧게 관리)"
            exit_price = round(snap.low_price, 0)
            exit_basis = "당일 저가 재이탈 시 매물 소화 실패로 판단, 즉시 후보 제외"
            if snap.program_net_buy_today > 0 and rise_from_low >= 0.03:
                verdict = "매수"
                action_timing = "즉시(장중 실시간) - 단, 지속성이 약한 케이스이므로 짧은 목표 관리 필수"
                reasons.append("프로그램 순매수 전환 확인, 저가 대비 반등폭 3% 이상")
            else:
                verdict = "관망"
                action_timing = "프로그램 매수 전환 및 저가 대비 반등폭 재확인 필요 - 실시간 모니터링"

    elif case_id == 4:
        if _missing(snap.current_price, snap.low_price, snap.open_price, snap.ma20):
            warnings.append("현재가/저가/시가/20일선 데이터 미확보")
        else:
            tail_ratio = (snap.current_price - snap.low_price) / snap.low_price if snap.low_price else 0
            near_ma20 = abs(snap.low_price - snap.ma20) / snap.ma20 <= 0.03 if snap.ma20 else False
            target_price = round(snap.ma20 * 1.08, 0) if snap.ma20 else None
            target_basis = "20일선 지지 확인 후 통상 회복 목표(+8%) 근사치"
            exit_price = round(snap.ma20 * 0.97, 0) if snap.ma20 else None
            exit_basis = "20일선 대비 -3% 초과 이탈 시 지지 실패로 판단, 후보 교체"
            if tail_ratio >= 0.03 and near_ma20 and snap.current_price >= snap.ma20:
                verdict = "매수"
                action_timing = "당일 종가(15:00~15:30) 아래꼬리 확정 확인 후, 익일 시가 갭 여부로 2차 확인"
                reasons.append("저가 대비 종가 반등폭 3% 이상 + 20일선 지지 확인")
            else:
                verdict = "관망"
                action_timing = "아래꼬리/20일선 지지 미확정 - 1주일 관망 후 재평가 (가장 낮은 확률군)"

    elif case_id == 5:
        if _missing(snap.current_price, snap.high_20d, snap.ma20, snap.volume, snap.prev_volume):
            warnings.append("현재가/최근20일고가/20일선/거래량 데이터 일부 미확보")
        else:
            supply_zone = snap.high_20d
            vol_ratio = (snap.volume / snap.prev_volume) if snap.prev_volume else None
            target_price = round(supply_zone * 1.08, 0)
            target_basis = "매물대(최근 20일 고가권) 돌파 기준 +8% 근사 목표"
            exit_price = round(snap.ma20, 0)
            exit_basis = "20일선(추세선) 이탈 시 눌림목 실패로 판단"
            if snap.current_price > supply_zone and snap.current_price > snap.ma20 and vol_ratio and vol_ratio >= 1.2:
                verdict = "매수"
                action_timing = "즉시(시초가 형성 후 30분~1시간, 9:30~10:30 확인 유리)"
                reasons.append("매물대 돌파 + 거래량 전일比 120% 이상 확인")
            else:
                verdict = "관망"
                action_timing = "매물대 돌파 시도 전 - 장중 실시간 관찰, 최대 3거래일 관망"

    elif case_id == 6:
        if _missing(snap.current_price, snap.low_price, snap.open_price, snap.ma60):
            warnings.append("현재가/저가/시가/60일선 데이터 일부 미확보 (지수 급락 여부는 별도 확인 필요)")
        else:
            drawdown_recover = (snap.current_price - snap.low_price) / snap.low_price if snap.low_price else 0
            near_support = abs(snap.current_price - snap.ma60) / snap.ma60 <= 0.03 if snap.ma60 else False
            target_price = round(snap.high_20d, 0) if snap.high_20d else None
            target_basis = "지수 반등 시 최근 전고점 회복을 목표로 근사"
            exit_price = round(snap.ma60 * 0.97, 0) if snap.ma60 else None
            exit_basis = "60일선 대비 -3% 초과 이탈 시 지지 실패"
            if drawdown_recover >= 0.02 and near_support and snap.inst_net_buy_1d and snap.inst_net_buy_1d > 0:
                verdict = "매수"
                action_timing = "지수 급락 당일에만 유효 - 즉시 확인, 낙폭 축소는 오후장(13:00 이후) 재확인"
                reasons.append("낙폭 축소 2% 이상 + 60일선 부근 지지 + 기관 순매수 확인")
            else:
                verdict = "관망"
                action_timing = "이 CASE는 지수 급락 당일에만 성립 - 해당 조건 아니면 판단 보류"

    elif case_id == 7:
        if _missing(snap.current_price, snap.high_20d, snap.ma5, snap.ma20, snap.volume, snap.prev_volume):
            warnings.append("현재가/최근고가/이평선/거래량 데이터 일부 미확보")
        else:
            near_high = abs(snap.current_price - snap.high_20d) / snap.high_20d <= 0.03 if snap.high_20d else False
            ma_converge = (abs(snap.ma5 - snap.ma20) / snap.ma20 <= 0.05) if (snap.ma5 and snap.ma20) else False
            vol_ratio = (snap.volume / snap.prev_volume) if snap.prev_volume else None
            target_price = round(snap.high_20d, 0) if snap.high_20d else None
            target_basis = "전고점 재돌파를 목표가로 설정 (매물 부담 적다고 가정한 근사치)"
            exit_price = round(min(snap.ma5, snap.ma20), 0) if (snap.ma5 and snap.ma20) else None
            exit_basis = "이평선 밀집대 하단 이탈 시 반등 실패로 판단"
            if near_high and ma_converge and vol_ratio and vol_ratio >= 1.0:
                verdict = "매수"
                action_timing = "종가 부근(14:30~15:20) 전고점 돌파 확정 여부 확인 후 진입"
                reasons.append("전고점 근접 + 이평선 밀집 + 거래량 전일 수준 이상 확인")
            else:
                verdict = "관망"
                action_timing = "전고점 돌파 시도 전 - 장중 지속 관찰, 최대 1주일 관망"

    elif case_id == 8:
        if _missing(snap.ma5, snap.ma10, snap.ma20):
            warnings.append("단기 이평선(5·10·20일) 데이터 미확보")
        else:
            aligned_up = snap.ma5 >= snap.ma10 >= snap.ma20
            target_price = None
            target_basis = "스윙/중기 케이스로 고정 목표가 대신 추세 유지 여부로 관리 권장 (10일선 기준 트레일링)"
            exit_price = round(snap.ma10, 0)
            exit_basis = "10일선(정배열 기준선) 종가 이탈 시 추세 훼손으로 판단, 후보 교체"
            if aligned_up and (snap.pension_net_buy_cum20 and snap.pension_net_buy_cum20 > 0):
                verdict = "매수"
                action_timing = "스윙 관점 - 즉시 진입보다 눌림목(단기 조정) 발생 시 분할 매수"
                reasons.append("5·10·20일선 정배열 우상향 + 연기금 누적 순매수 확인")
            elif aligned_up:
                verdict = "관망"
                action_timing = "정배열은 확인되나 연기금 매집 데이터 미확인 - 스크리닝 후보로만 관리"
            else:
                verdict = "관망"
                action_timing = "정배열 조건 미충족"

    elif case_id == 9:
        if _missing(snap.current_price, snap.ma60):
            warnings.append("현재가/60일선 데이터 미확보")
        else:
            above_ma60 = snap.current_price >= snap.ma60
            target_price = None
            target_basis = "스윙/중기 케이스 - 저점 상향 추세 유지 시 목표가 대신 60일선 트레일링 관리 권장"
            exit_price = round(snap.ma60, 0)
            exit_basis = "60일선(종가 기준) 이탈 시 추세 훼손으로 판단, 후보 교체"
            if above_ma60 and (snap.pension_net_buy_cum20 and snap.pension_net_buy_cum20 > 0):
                verdict = "적극매수"
                action_timing = "스윙 관점 - 눌림목(단기 조정) 발생 시 아무 때나 분할 진입 가능"
                reasons.append("60일선 위 우상향 유지 + 연기금 누적 순매수 확인")
            elif above_ma60:
                verdict = "매수"
                action_timing = "60일선 우상향은 확인되나 연기금 매집 데이터 미확인 - 데이터 보강 후 재평가"
            else:
                verdict = "관망"
                action_timing = "60일선 하회 - 추세 훼손 상태, 후보 제외"

    elif case_id == 10:
        if _missing(snap.current_price, snap.high_20d, snap.low_20d):
            warnings.append("현재가/최근20일 고가·저가 데이터 미확보")
        else:
            pullback = (snap.high_20d - snap.current_price) / snap.high_20d if snap.high_20d else 0
            near_prior_high_fail = 0.01 <= pullback <= 0.08
            target_price = round(snap.high_20d, 0)
            target_basis = "직전 전고점 재돌파를 목표가로 설정"
            exit_price = round(snap.low_20d, 0) if snap.low_20d else None
            exit_basis = "최근 저점 하회 시 저점 상향 구조 붕괴로 판단, 후보 교체"
            both_buy = bool(snap.foreign_net_buy_1d and snap.foreign_net_buy_1d > 0 and snap.inst_net_buy_1d and snap.inst_net_buy_1d > 0)
            if near_prior_high_fail and both_buy:
                verdict = "매수"
                action_timing = "종가 확정(14:30~15:20) 후 기관·외인 동반 순매수 최종 확정치 재확인"
                reasons.append("전고점 -1%~-8% 구간 + 기관·외국인 동반 순매수 확인")
            else:
                verdict = "관망"
                action_timing = "저점 상향 및 동반 순매수 재확인 필요 - 종가 기준 재평가"

    elif case_id == 11:
        if _missing(snap.current_price, snap.high_60d, snap.low_60d, snap.ma120, snap.volume, snap.prev_volume):
            warnings.append("현재가/60일 고저/120일선/거래량 데이터 일부 미확보")
        else:
            box_height = snap.high_60d - snap.low_60d
            box_top = snap.high_60d
            vol_ratio = (snap.volume / snap.prev_volume) if snap.prev_volume else None
            target_price = round(box_top + box_height, 0)  # 박스권 폭 이론(박스 높이만큼 추가 상승)
            target_basis = "박스권 상단 돌파 + 박스 높이만큼 추가 상승(박스권 폭 이론) 근사 목표"
            exit_price = round(snap.ma60, 0) if snap.ma60 else round(box_top * 0.97, 0)
            exit_basis = "60일선 이탈 시 박스권 지지 붕괴로 판단, 후보 교체"
            if snap.current_price >= box_top * 0.98 and vol_ratio and vol_ratio >= 1.5:
                verdict = "매수"
                action_timing = "즉시(오전 9:30~11:00 우선 확인, 종가 14:30~15:20 재확인)"
                reasons.append("박스권 상단 근접/돌파 + 거래량 전일比 150% 이상")
            else:
                verdict = "관망"
                action_timing = "박스권 상단 돌파 시도 전 - 장중 실시간 관찰, 최대 1주일 관망"

    # ---- 데이터 신뢰도 표기 ----
    if warnings:
        data_confidence = "일부 미확보" if reasons or target_price is not None else "판단불가(데이터 부족)"
        if not reasons and target_price is None:
            verdict = "판단불가"
            action_timing = "데이터 미확보로 판단 보류 - 재조회 필요"
    else:
        data_confidence = "실측"

    return CaseVerdict(
        case_id=case_id,
        stock_code=snap.stock_code,
        stock_name=snap.stock_name,
        verdict=verdict,
        action_timing=action_timing,
        current_price=snap.current_price,
        target_price=target_price,
        target_basis=target_basis,
        exit_price=exit_price,
        exit_basis=exit_basis,
        supply_demand_note=supply_demand_note,
        reasons=reasons,
        warnings=warnings,
        prohibited_actions=list(COMMON_PROHIBITED_ACTIONS),
        data_confidence=data_confidence,
    )


def rank_top5(verdicts_by_case: Dict[int, List[CaseVerdict]]) -> List[CaseVerdict]:
    """CASE 우선순위(9->8->1->2->10->11->5->6->7->3->4) 순서대로 훑으며
    verdict 가 '적극매수' 또는 '매수' 인 종목을 TOP5까지 채운다.
    각 CASE 내부에서는 '적극매수'를 '매수'보다 우선한다.
    50% 미만 확률군(순위 하위) 및 '관망'/'판단불가'는 채우지 않는다 (빈 자리는 '해당 CASE 조건 충족 종목 없음')."""
    order_score = {"적극매수": 2, "매수": 1}
    result: List[CaseVerdict] = []
    seen_codes = set()

    for cid in CASE_PRIORITY_ORDER:
        candidates = [v for v in verdicts_by_case.get(cid, []) if v.verdict in order_score]
        candidates.sort(key=lambda v: order_score[v.verdict], reverse=True)
        for v in candidates:
            if v.stock_code in seen_codes:
                continue
            result.append(v)
            seen_codes.add(v.stock_code)
            if len(result) >= 5:
                return result
    return result


# ---------------------------------------------------------------------------
# 종목 품질 필터 (거래 가능 우량 종목 한정 / 동전주 제외)
# ---------------------------------------------------------------------------
DEFAULT_MIN_PRICE = 1000            # 이 가격 미만은 "동전주"로 간주해 제외 (기본값, 조정 가능)
DEFAULT_MIN_AVG_TRADING_VALUE = 1_000_000_000  # 최근 5일 평균 거래대금 최소 기준(원) - 유동성 없는 종목 제외용 근사 기준


def is_penny_stock(snap: "LiveSnapshot", min_price: int = DEFAULT_MIN_PRICE) -> bool:
    """동전주 여부. 가격 데이터가 없으면(조회 실패) 판단할 수 없으므로 False를 반환해
    '동전주라서 제외'가 아니라 '데이터 없어서 어차피 평가 불가'로 상위 로직이 별도 처리하게 한다."""
    if snap.current_price is None:
        return False
    return snap.current_price < min_price


def passes_blue_chip_filter(
    snap: "LiveSnapshot",
    min_price: int = DEFAULT_MIN_PRICE,
    min_avg_trading_value: float = DEFAULT_MIN_AVG_TRADING_VALUE,
) -> bool:
    """'거래 가능 우량 종목'으로 볼 수 있는지의 근사 기준.
    주의: 관리종목/거래정지/투자유의종목 여부를 직접 조회하는 것은 KIS 응답의 정확한 필드명을
    100% 확신할 수 없어 이 함수에 넣지 않았다(잘못된 필드명으로 조용히 걸러지지 않는 것을 방지).
    대신 가격(동전주 제외)과 최근 평균 거래대금(유동성)만으로 근사 필터링한다."""
    if snap.current_price is None:
        return False
    if is_penny_stock(snap, min_price=min_price):
        return False
    if snap.avg_trading_value_5d is not None and snap.avg_trading_value_5d < min_avg_trading_value:
        return False
    return True


# ---------------------------------------------------------------------------
# 기술적 지표 계산 (RSI / ATR) - daily_prices(get_daily_prices 반환값, 최신순)만으로 계산
# ---------------------------------------------------------------------------
def compute_rsi(daily_prices: Optional[List[Dict[str, Any]]], period: int = 14) -> Optional[float]:
    """RSI(상대강도지수). daily_prices는 최신순으로 정렬되어 있다고 가정(kis_client.get_daily_prices와 동일).
    데이터가 부족하면 None(판단불가)을 반환한다 - 임의의 숫자를 채우지 않는다."""
    if not daily_prices or len(daily_prices) < period + 1:
        return None
    closes = []
    for row in daily_prices[: period + 1]:
        c = row.get("stck_clpr")
        if c is None:
            return None
        try:
            closes.append(float(c))
        except (TypeError, ValueError):
            return None
    # daily_prices는 최신이 [0]이므로, 오래된 순으로 뒤집어서 통상적인 RSI 계산 순서로 처리
    closes = list(reversed(closes))
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def compute_atr(daily_prices: Optional[List[Dict[str, Any]]], period: int = 14) -> Optional[float]:
    """ATR(Average True Range) - 변동성 기반 손절폭 산출에 사용. 데이터 부족 시 None."""
    if not daily_prices or len(daily_prices) < period + 1:
        return None
    rows = daily_prices[: period + 1]
    true_ranges = []
    try:
        for i in range(len(rows) - 1):
            high = float(rows[i]["stck_hgpr"])
            low = float(rows[i]["stck_lwpr"])
            prev_close = float(rows[i + 1]["stck_clpr"])
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
    except (KeyError, TypeError, ValueError):
        return None
    if not true_ranges:
        return None
    return round(sum(true_ranges) / len(true_ranges), 1)


def count_consecutive_net_buy_days(investor_rows: Optional[List[Dict[str, Any]]], field: str) -> int:
    """investor_rows(get_investor_trend 반환값, 최신순)에서 지정한 필드(외국인 또는 기관 순매수량)가
    오늘부터 며칠 연속 순매수(양수)인지 센다. 데이터가 없으면 0을 반환한다(판단불가와 동일하게 취급)."""
    if not investor_rows:
        return 0
    count = 0
    for row in investor_rows:
        try:
            val = float(row.get(field))
        except (TypeError, ValueError):
            break
        if val > 0:
            count += 1
        else:
            break
    return count
