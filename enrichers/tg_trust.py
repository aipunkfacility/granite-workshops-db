# enrichers/tg_trust.py
import requests
import time
from loguru import logger
from utils import adaptive_delay
from enrichers.tg_finder import _tg_request


_TG_MAX_RETRIES = 5
_TG_INITIAL_BACKOFF = 5


def check_tg_trust(url: str) -> dict:
    """Анализирует Telegram-профиль: живой ли это контакт."""
    if not url:
        return {"trust_score": 0}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    result = {
        "has_avatar": False,
        "has_description": False,
        "is_bot": False,
        "is_channel": False,
        "trust_score": 0,
    }

    r = _tg_request(url, headers)
    if not r:
        return result

    html = r.text

    if "tgme_page_photo_image" in html:
        result["has_avatar"] = True
        result["trust_score"] += 1

    if "tgme_page_description" in html:
        result["has_description"] = True
        result["trust_score"] += 1

    if "tgme_page_extra" in html and (
        "subscribers" in html or "members" in html
    ):
        result["is_channel"] = True
        result["trust_score"] -= 1

    if "tgme_page_extra" in html and "bot" in html.lower():
        result["is_bot"] = True
        result["trust_score"] -= 1

    adaptive_delay(1.0, 2.0)
    return result
