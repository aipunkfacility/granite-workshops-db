# enrichers/messenger_scanner.py
import re
from loguru import logger
from utils import fetch_page
from requests.exceptions import RequestException

class MessengerScanner:
    """Сканирует сайт на наличие ссылок на мессенджеры и соцсети."""

    def __init__(self, config: dict):
        self.config = config
        enrichment_config = config.get("enrichment", {})
        self.pages_to_scan = enrichment_config.get("messenger_pages", ["/", "/contacts"])

    def scan_website(self, base_url: str) -> dict:
        """Сканирует несколько страниц сайта в поисках виджетов и ссылок."""
        found_messengers: dict = {}

        if not base_url:
            return found_messengers

        base_url_clean = base_url.rstrip("/")

        for page in self.pages_to_scan:
            url = f"{base_url_clean}{page}"
            try:
                html = fetch_page(url, timeout=10)
                messengers = self._extract_social_links(html)
                
                for k, v in messengers.items():
                    if v and k not in found_messengers:
                        found_messengers[k] = v

                # Если нашли все основные — можно не проверять остальные страницы
                if "telegram" in found_messengers and "whatsapp" in found_messengers:
                    break

            except RequestException:
                # Если страница недоступна (напр. 404 для /contacts), просто игнорируем
                continue
            except Exception as e:
                logger.debug(f"Ошибка при сканировании {url}: {e}")

        return found_messengers

    def _extract_social_links(self, html: str) -> dict:
        """Парсинг ссылок из HTML."""
        result = {}
        if not html:
            return result

        # Telegram
        # https://t.me/username, https://telegram.me/username
        tg_match = re.search(r"href=['\"](https?://(?:t\.me|telegram\.me)/[^'\"]+)['\"]", html)
        if tg_match:
            result["telegram"] = tg_match.group(1)

        # WhatsApp
        # https://wa.me/7... https://api.whatsapp.com/send?phone=7...
        wa_match = re.search(r"href=['\"](https?://(?:wa\.me|api\.whatsapp\.com/send\?phone=)[^'\"]+)['\"]", html)
        if wa_match:
            result["whatsapp"] = wa_match.group(1)

        # VK
        vk_match = re.search(r"href=['\"](https?://(?:www\.)?vk\.com/[^'\"]+)['\"]", html)
        if vk_match:
            result["vk"] = vk_match.group(1)

        # OK
        ok_match = re.search(r"href=['\"](https?://(?:www\.)?ok\.ru/[^'\"]+)['\"]", html)
        if ok_match:
            result["ok"] = ok_match.group(1)

        return result
