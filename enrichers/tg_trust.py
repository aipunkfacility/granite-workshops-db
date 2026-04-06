# enrichers/tg_trust.py
import requests
from loguru import logger
from utils import adaptive_delay


def check_tg_trust(url: str) -> dict:
    """Анализирует Telegram-профиль: живой ли это контакт.

    Возвращает dict с флагами и trust_score.
    trust_score >= 2 — живой бизнес-контакт.
    trust_score == 0 — мёртвый/фейк.
    """
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

    try:
        r = requests.get(url, headers=headers, timeout=10)
        html = r.text

        # Аватарка → живой профиль
        if "tgme_page_photo_image" in html:
            result["has_avatar"] = True
            result["trust_score"] += 1

        # Описание → заполненный профиль
        if "tgme_page_description" in html:
            result["has_description"] = True
            result["trust_score"] += 1

        # Канал/группа — нельзя написать в личку, хуже как контакт
        if "tgme_page_extra" in html and (
            "subscribers" in html or "members" in html
        ):
            result["is_channel"] = True
            result["trust_score"] -= 1  # штраф: канал, не личный контакт

        # Бот — не живой человек
        if "tgme_page_extra" in html and "bot" in html.lower():
            result["is_bot"] = True
            result["trust_score"] -= 1

        adaptive_delay(1.0, 2.0)

    except Exception as e:
        logger.debug(f"Ошибка проверки траста TG {url}: {e}")

    return result
