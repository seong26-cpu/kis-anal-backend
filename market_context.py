# -*- coding: utf-8 -*-
"""
market_context.py (스텁)
=========================
closing_bet.py 가 기대하는 인터페이스: kosdaq_is_up() -> bool | None
None = 조회 실패("판단불가"), True/False = 실측 결과

TODO: FinanceDataReader 또는 kis_client.get_current_price_raw("KOSDAQ 지수코드")로 교체
"""

from typing import Optional


def kosdaq_is_up() -> Optional[bool]:
    try:
        import FinanceDataReader as fdr  # pip install finance-datareader (선택 설치)
        df = fdr.DataReader("KQ11")
        if len(df) < 2:
            return None
        return bool(df["Close"].iloc[-1] > df["Close"].iloc[-2])
    except Exception:
        return None
