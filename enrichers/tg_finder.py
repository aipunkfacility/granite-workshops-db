# enrichers/tg_finder.py
import re
from utils import adaptive_delay, TRANSLIT_MAP
import requests
from loguru import logger


def _translit(text: str) -> str:
    """Транслитерация кириллицы в латиницу. Использует тот же словарь что и slugify()."""
    text = text.lower()
    for cyr, lat in TRANSLIT_MAP:
        text = text.replace(cyr, lat)
    return text

def find_tg_by_phone(phone: str, config: dict) -> str | None:
    """Метод 1: Прямая привязка телефона (t.me/+7XXX)."""
    if not phone or len(phone) < 11:
        return None
    
    # Исправление бага 7
    enrich_config = config.get("enrichment", {})
    tg_config = enrich_config.get("tg_finder", {})
    tg_delay = tg_config.get("check_delay", 1.5)

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    url = f"https://t.me/+{phone}"
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        # Контакту соответствует кнопка "Send Message" или заголовок "Telegram: Contact"
        has_button = "tgme_action_button_new" in r.text
        has_contact_title = "Telegram: Contact" in r.text
        if has_button or has_contact_title:
            adaptive_delay(tg_delay, tg_delay + 1.0)
            return url
    except Exception as e:
        logger.warning(f"TG find by phone error: {e}")
    return None


def generate_usernames(name: str, phone: str = None) -> list[str]:
    """Метод 2: Генерация юзернеймов из названия и телефона."""
    base = _translit(name)
    base = re.sub(r'[^a-z0-9]', '', base)
    
    if not base:
        return []

    variants = [
        base[:30],
        base.replace('ritualnyeuslugi', 'ritual')[:30],
        f"{base[:20]}_ritual",
        f"ritual_{base[:20]}",
    ]
    
    if phone and len(phone) >= 11:
        variants.append(f"{base[:15]}{phone[-4:]}")
        variants.append(phone) 
        
    # Возвращаем уникальные
    # Сохраняем порядок
    seen = set()
    result = []
    for v in variants:
        if v not in seen and len(v) >= 5:
            seen.add(v)
            result.append(v)
            
    return result


def find_tg_by_name(name: str, phone: str, config: dict) -> str | None:
    """Генерация и проверка юзернеймов."""
    enrich_config = config.get("enrichment", {})
    tg_config = enrich_config.get("tg_finder", {})
    tg_delay = tg_config.get("check_delay", 1.5)

    variants = generate_usernames(name, phone)
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for v in variants:
        try:
            r = requests.get(f"https://t.me/{v}", headers=headers, timeout=8)
            adaptive_delay(tg_delay, tg_delay + 0.5)
            
            if "tgme_page_title" in r.text:
                m1 = re.search(r'tgme_page_description[^>]*>([^<]+)', r.text)
                desc = m1.group(1).lower() if m1 else ""
                
                m2 = re.search(r'tgme_page_title[^>]*>([^<]+)', r.text)
                title = m2.group(1).lower() if m2 else ""
                
                keywords = ['ритуал', 'похорон', 'памятник', 'мемориал', 'funeral', 'angel']
                
                if any(k in desc for k in keywords) or any(k in title for k in keywords):
                    return f"https://t.me/{v}"
        except Exception:
            pass
            
    return None
