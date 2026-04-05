# utils.py
import re
import time
import random
from urllib.parse import urlparse
from rapidfuzz import fuzz
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
import requests
from fake_useragent import UserAgent
from loguru import logger

ua = UserAgent()


def slugify(text: str) -> str:
    """Транслитерация кириллицы в латиницу для URL (slug).
    Пример: "Волгоград" -> "volgograd", "Санкт-Петербург" -> "sankt-peterburg"
    """
    if not text:
        return ""
    
    cyr = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
    lat = 'abvgdeezzijklmnoprstufhccssyyeyua'
    trans = str.maketrans(cyr, lat)
    
    # Доп замены для сложных случаев
    text = text.lower().replace('ё', 'e').replace('ж', 'zh').replace('х', 'h')\
               .replace('ц', 'c').replace('ч', 'ch').replace('ш', 'sh').replace('щ', 'sh')\
               .replace('ю', 'yu').replace('я', 'ya')
               
    text = text.translate(trans)
    # Очистка от спецсимволов, замена пробелов на дефис
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s]+', '-', text).strip('-')
    
    return text
def adaptive_delay(min_sec: float = 1.0, max_sec: float = 3.5) -> float:
    """Случайная задержка между запросами. Имитирует поведение человека.

    Диапазон по умолчанию 1.0–3.5с вместо фиксированного sleep.
    Для Telegram использовать min=1.5 (из config: tg_finder.check_delay).
    """
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)
    return delay


def normalize_phone(phone: str) -> str | None:
    """Нормализация телефона к формату E.164: 7XXXXXXXXXX (без +).

    Обрабатывает: +79031234567, 89031234567, 9031234567,
                  +7 (903) 123-45-67, 8 (903) 123 45 67
    Возвращает: "79031234567" или None
    """
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    # Если начинается с 8 (российский формат) — заменяем на 7
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    # Если 10 цифр — добавляем 7 (местный номер)
    elif len(digits) == 10:
        digits = "7" + digits
    # Проверяем валидность: 11 цифр, начинается с 7
    if digits.startswith("7") and len(digits) == 11:
        return digits
    return None


def normalize_phones(phones: list[str]) -> list[str]:
    """Нормализация списка телефонов с дедупликацией."""
    result = []
    seen = set()
    for p in phones:
        norm = normalize_phone(p)
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def extract_emails(text: str) -> list[str]:
    """Извлечение email из текста."""
    if not text:
        return []
    return list(set(re.findall(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        text, re.IGNORECASE
    )))


def extract_domain(url: str) -> str | None:
    """Извлечение домена из URL."""
    if not url:
        return None
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.netloc.lower().replace("www.", "")
        return domain if domain else None
    except Exception:
        return None


def compare_names(name_a: str, name_b: str, threshold: int = 88) -> bool:
    """Сравнение названий компаний. Возвращает True если схожи выше порога.

    Использует token_sort_ratio из rapidfuzz — устойчив к перестановке слов:
    "Гранит-Мастер Иванов" ≈ "Иванов Гранит-Мастер"
    """
    if not name_a or not name_b:
        return False
    a = name_a.lower().strip()
    b = name_b.lower().strip()
    # Точное совпадение (после нормализации)
    if a == b:
        return True
    # Fuzzy match
    score = fuzz.token_sort_ratio(a, b)
    return score >= threshold


def extract_street(address: str) -> str:
    """Базовое извлечение улицы из адреса.

    "г. Новосибирск, ул. Ленина, 45" → "ленина"
    "Новосибирск, проспект Маркса 12" → "маркса"
    """
    if not address:
        return ""
    address_lower = address.lower()
    # Убираем город
    for prefix in ["г. ", "город "]:
        if prefix in address_lower:
            address_lower = address_lower.split(prefix, 1)[-1]
            break
    # Извлекаем улицу
    match = re.search(r"(?:ул\.?|улица|пр-т\.?|проспект|пер\.?|переулок)\s*(.+?)[,\d]", address_lower)
    if match:
        return match.group(1).strip()
    return address_lower.split(",")[0].strip() if "," in address_lower else address_lower


# ===== HTTP-запросы с retry =====

class NetworkError(Exception):
    """Сайт не отвечает после всех попыток."""
    pass


class SiteNotFoundError(Exception):
    """Сайт возвращает 404 — не нужно повторять."""
    pass


# Retry для временных ошибок (502, 503, timeout, connection)
# НЕ retry для 404 и 403 (заблокировали)
def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, SiteNotFoundError):
        return False
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        if response is not None and response.status_code in (403, 404):
            return False
    return True


# ИСПРАВЛЕНО: retry_if_exception (callable) вместо retry_if_exception_type (тип)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception(_should_retry),
    reraise=True,
)
def fetch_page(url: str, timeout: int = 15) -> str:
    """Получение HTML страницы с retry и логированием.

    Raises:
        NetworkError: после 3 неудачных попыток
        SiteNotFoundError: при 404
    """
    headers = {"User-Agent": ua.random}
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if response.status_code == 404:
            logger.warning(f"404 — {url}")
            raise SiteNotFoundError(f"404: {url}")
        response.raise_for_status()
        return response.text
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Connection error: {url} — {e}")
        raise NetworkError(f"Connection failed: {url}") from e
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout: {url}")
        raise NetworkError(f"Timeout: {url}")
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP {e.response.status_code}: {url}")
        raise


def check_site_alive(url: str) -> int | None:
    """HEAD-запрос для проверки, живой ли сайт. Возвращает статус-код или None."""
    if not url:
        return None
    try:
        headers = {"User-Agent": ua.random}
        r = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
        return r.status_code
    except Exception:
        return None


def pick_best_value(*values: str) -> str:
    """Из нескольких значений берёт самое длинное (полное)."""
    candidates = [v.strip() for v in values if v and v.strip()]
    if not candidates:
        return ""
    return max(candidates, key=len)
