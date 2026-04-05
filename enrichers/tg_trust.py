# enrichers/tg_trust.py
import requests
import re
from loguru import logger
from utils import adaptive_delay

def check_tg_trust(url: str) -> dict:
    """Анализирует Telegram-профиль и присваивает очки 'доверия'.
    
    Чем больше заполнен профиль — тем выше вероятность, что он живой/официальный.
    Возвращает dict с флагами и счетчиком trust_score.
    """
    if not url:
        return {"trust_score": 0}

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    result = {
        "has_avatar": False,
        "has_description": False,
        "is_channel": False,  
        "subscribers": 0,
        "trust_score": 0
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        html = r.text
        
        # Наличие аватарки (есть класс tgme_page_photo_image)
        if "tgme_page_photo_image" in html:
            result["has_avatar"] = True
            result["trust_score"] += 1
            
        # Наличие описания
        if "tgme_page_description" in html:
            result["has_description"] = True
            result["trust_score"] += 1
            
        # Количество подписчиков (если это канал/группа)
        sub_match = re.search(r'<div class="tgme_page_extra">[^<]*([\d\s]+)\s*(subscribers|members)', html)
        if sub_match:
            result["is_channel"] = True
            subs_str = re.sub(r'\D', '', sub_match.group(1))
            subs = int(subs_str) if subs_str else 0
            result["subscribers"] = subs
            
            if subs > 10:
                result["trust_score"] += 1
            if subs > 100:
                result["trust_score"] += 1
                
        adaptive_delay(1.0, 2.0)
        
    except Exception as e:
        logger.debug(f"Ошибка проверки траста TG {url}: {e}")
        
    return result
