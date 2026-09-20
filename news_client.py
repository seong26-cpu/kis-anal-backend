# -*- coding: utf-8 -*-
"""
news_client.py (스텁)
======================
closing_bet.py 가 기대하는 인터페이스: search_recent_news(stock_name) -> List[dict] | None
- 반환 None  = API 미연동/조회 실패 → closing_bet.py가 "판단불가"로 표시
- 반환 []    = 조회는 됐지만 결과 없음 → closing_bet.py가 "❌"로 표시
- 반환 [...] = 기사 리스트 → closing_bet.py가 "✅"로 표시 (내용은 사람이 직접 확인)

TODO: NAVER_CLIENT_ID/SECRET 발급 후 실제 네이버 뉴스 검색 API(openapi.naver.com/v1/search/news.json) 연동
"""

import requests
import config_store


def search_recent_news(stock_name: str):
    client_id, client_secret = config_store.get_naver_news_keys()
    if not client_id or not client_secret or not stock_name:
        return None
    try:
        res = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
            params={"query": stock_name, "display": 10, "sort": "date"},
            timeout=5,
        )
        res.raise_for_status()
        items = res.json().get("items", [])
        return [{"title": it.get("title"), "link": it.get("link"), "pubDate": it.get("pubDate")} for it in items]
    except requests.RequestException:
        return None
