# -*- coding: utf-8 -*-
"""
market_data_crawler.py
=======================
API 키 없이, 신뢰 가능한 공개 사이트(네이버 금융)를 직접 크롤링해서
뉴스/시황/업종(섹터) 데이터를 가져온다.

⚠️ 중요: 이 파일의 파싱 로직은 이 개발 환경(컨테이너)에서 외부망이 막혀 있어
   실제 finance.naver.com 응답으로 직접 테스트하지 못했다. 배포(Render) 후
   반드시 아래 엔드포인트들을 한 번씩 직접 호출해 정상적으로 파싱되는지
   확인해야 한다 (페이지 마크업이 바뀌면 파싱이 깨질 수 있음 — 이 파일은
   모든 함수가 파싱 실패 시 예외를 던지지 않고 None/빈 리스트를 반환하도록
   방어적으로 작성했다. 즉 최악의 경우도 "판단불가"로 귀결되지, 서버가
   죽거나 엉뚱한 데이터를 지어내지 않는다).

절대 원칙
---------
- 크롤링 실패/구조 변경 시 None 또는 빈 리스트를 반환한다. 임의로 데이터를 만들지 않는다.
- 이 사이트의 저작물(기사 본문)을 그대로 복제하지 않는다 — 제목/링크/날짜만 가져오고,
  본문은 원문 링크로 연결한다.
"""

import re
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_BASE = "https://finance.naver.com"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}


def _get(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 6) -> Optional[str]:
    try:
        res = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
        res.raise_for_status()
        res.encoding = res.apparent_encoding or "euc-kr"
        return res.text
    except requests.RequestException:
        return None


def _extract_news_links(html: str, limit: int) -> List[Dict[str, str]]:
    """네이버 금융 뉴스 페이지 공통 파서. 기사 리더(news_read.naver) 링크를 가진
    <a> 태그를 기준으로 추출 — 페이지 markup(클래스명)이 바뀌어도 비교적 안정적."""
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    results = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "news_read.naver" not in href and "article_id=" not in href.lower():
            continue
        title = a.get_text(strip=True)
        if not title or href in seen:
            continue
        seen.add(href)
        results.append({"title": title, "link": urljoin(_BASE, href)})
        if len(results) >= limit:
            break
    return results


def resolve_stock_code(query: str, limit: int = 5) -> Optional[List[Dict[str, str]]]:
    """회사명 → 종목코드 변환. 네이버 증권 자동완성 API(공개, 인증 불필요) 사용.
    검색창에 종목명을 입력했을 때 코드로 바꾸는 용도. 실패 시 None."""
    if not query:
        return None
    try:
        res = requests.get(
            "https://m.stock.naver.com/front-api/search/autoComplete",
            params={"query": query, "target": "stock,index,marketindicator,coin,ipo"},
            headers=_HEADERS, timeout=5,
        )
        res.raise_for_status()
        data = res.json()
        items = (data.get("result") or {}).get("items") or []
        results = []
        for it in items:
            code, name = it.get("code"), it.get("name")
            if code and name and re.fullmatch(r"\d{6}", code):
                results.append({"code": code, "name": name, "market": it.get("typeName") or ""})
            if len(results) >= limit:
                break
        return results
    except (requests.RequestException, ValueError):
        return None


def fetch_stock_news(code: str, limit: int = 6) -> Optional[List[Dict[str, str]]]:
    """종목별 뉴스 — 네이버 금융 개별 종목 뉴스 탭 크롤링. 실패 시 None."""
    html = _get(f"{_BASE}/item/news_news.naver", params={"code": code, "page": 1})
    if html is None:
        return None
    items = _extract_news_links(html, limit)
    return items  # 빈 리스트일 수 있음(뉴스 없음) — 이는 None과 구분되는 정상 결과


def fetch_market_news(limit: int = 10) -> Optional[List[Dict[str, str]]]:
    """시황 뉴스 — 네이버 금융 증시 메인뉴스 크롤링. 실패 시 None."""
    html = _get(f"{_BASE}/news/mainnews.naver")
    if html is None:
        return None
    return _extract_news_links(html, limit)


def fetch_sector_rankings(limit: int = 60) -> Optional[List[Dict[str, Any]]]:
    """업종(섹터)별 등락률 — 네이버 금융 업종별시세 페이지 크롤링. 실패 시 None.
    반환: [{"sector": str, "changeRate": float, "link": str}, ...]
    ⚠️ 대표종목/거래대금까지는 이 목록 페이지에 없어서 미포함 — 필요하면
       각 업종 상세페이지(sise_group_detail.naver)를 추가로 크롤링해야 함(TODO)."""
    html = _get(f"{_BASE}/sise/sise_group.naver", params={"type": "upjong"})
    if html is None:
        return None
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "sise_group_detail.naver" not in href:
            continue
        name = a.get_text(strip=True)
        if not name or name in seen:
            continue
        tr = a.find_parent("tr")
        row_text = tr.get_text(" ", strip=True) if tr else ""
        m = re.search(r'([+-]?\d+\.\d+)\s*%', row_text)
        change_rate = float(m.group(1)) if m else None
        seen.add(name)
        rows.append({"sector": name, "changeRate": change_rate, "link": urljoin(_BASE, href)})
        if len(rows) >= limit:
            break
    return rows
