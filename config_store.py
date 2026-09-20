# -*- coding: utf-8 -*-
"""
config_store.py
================
모든 API 키/계좌정보는 이 모듈을 통해서만 읽는다. 코드 어디에도 직접 하드코딩하지 않는다.
"""

import os
from typing import Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 배포 환경(Render 등)에서는 플랫폼 환경변수를 직접 사용하므로 dotenv 불필요


def get_kis_keys() -> Tuple[Optional[str], Optional[str]]:
    """실전투자 KIS_APPKEY / KIS_APPSECRET 반환. 미설정 시 (None, None)."""
    return os.environ.get("KIS_APPKEY"), os.environ.get("KIS_APPSECRET")


def has_kis_keys() -> bool:
    k, s = get_kis_keys()
    return bool(k) and bool(s)


def get_kis_account() -> Tuple[Optional[str], Optional[str]]:
    """계좌번호 앞 8자리(CANO) / 뒤 2자리(ACNT_PRDT_CD). 주문/잔고 조회 API에서 필요."""
    return os.environ.get("KIS_CANO"), os.environ.get("KIS_ACNT_PRDT_CD")


def get_kis_mode() -> str:
    """'prod'(실전투자) 또는 'vts'(모의투자). 기본값 prod."""
    return os.environ.get("KIS_MODE", "prod").lower()


def get_dart_api_key() -> Optional[str]:
    return os.environ.get("DART_API_KEY")


def get_naver_news_keys() -> Tuple[Optional[str], Optional[str]]:
    return os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
