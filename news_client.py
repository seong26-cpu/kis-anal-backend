# -*- coding: utf-8 -*-
"""
news_client.py
===============
closing_bet.py 가 기대하는 인터페이스: search_recent_news(stock_name) -> List[dict] | None
API 키 없이 네이버 뉴스 검색 결과 페이지를 직접 크롤링한다 (신뢰 가능한 언론사 기사 색인).

- 반환 None  = 크롤링 실패(네트워크/파싱 오류) → closing_bet.py가 "판단불가"로 표시
- 반환 []    = 조회는 됐지만 결과 없음 → closing_bet.py가 "❌"로 표시
- 반환 [...] = 기사 리스트 → closing_bet.py가 "✅"로 표시 (내용은 사람이 직접 확인)

⚠️ 이 컨테이너는 외부망이 막혀 있어 실제 검색결과 페이지로 직접 테스트하지 못했다.
   배포 후 확인 필요 (마크업이 바뀌면 파싱이 실패할 수 있음 — 실패 시 None 반환하므로
   서버가 죽거나 데이터를 지어내지는 않는다).
"""

from typing import Optional, List, Dict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}


def search_recent_news(stock_name: str, limit: int = 8) -> Optional[List[Dict[str, str]]]:
    if not stock_name:
        return None
    try:
        res = requests.get(
            "https://search.naver.com/search.naver",
            params={"where": "news", "query": stock_name, "sort": "1"},  # sort=1: 최신순
            headers=_HEADERS, timeout=6,
        )
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        seen, results = set(), []
        # 네이버 뉴스 검색 결과의 기사 제목 링크(클래스명은 바뀔 수 있어 구조 기반으로 넓게 탐색)
        candidates = soup.select("a.news_tit") or soup.find_all("a", href=True)
        for a in candidates:
            href = a.get("href", "")
            title = a.get_text(strip=True) or a.get("title", "")
            if not href.startswith("http") or not title or href in seen:
                continue
            seen.add(href)
            results.append({"title": title, "link": urljoin("https://search.naver.com", href)})
            if len(results) >= limit:
                break
        return results
    except requests.RequestException:
        return None
