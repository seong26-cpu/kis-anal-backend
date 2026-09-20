# -*- coding: utf-8 -*-
"""
dart_client.py (스텁)
======================
closing_bet.py 가 기대하는 인터페이스:
- search_recent_disclosures(stock_code, dart_key, days) -> List[dict]
- has_recent_major_shareholder_disclosure(stock_code, dart_key, days) -> (bool|None, List[dict])

DART_API_KEY 미설정 시 항상 "판단불가"에 대응하는 값(None / 빈 리스트)을 반환한다.
TODO: DART Open API(opendart.fss.or.kr) 연동 — 공시 목록/대주주 지분변동 공시 필터링 구현
"""

from typing import Optional, List, Dict, Any, Tuple


def search_recent_disclosures(stock_code: str, dart_key: Optional[str], days: int = 14) -> List[Dict[str, Any]]:
    if not dart_key:
        return []
    # TODO: opendart.fss.or.kr/api/list.json 호출 후 최근 N일 필터링
    return []


def has_recent_major_shareholder_disclosure(
    stock_code: str, dart_key: Optional[str], days: int = 14
) -> Tuple[Optional[bool], List[Dict[str, Any]]]:
    if not dart_key:
        return None, []
    # TODO: 대주주/특수관계인 지분변동 공시(대량보유상황보고서 등) 필터링 구현
    return False, []
