# scrapers/firmsru.py — рефакторинг части Firmsru из scripts/scrape_city.py
from scrapers.base import BaseScraper
from models import RawCompany, Source
from utils import normalize_phones, extract_emails, adaptive_delay
from loguru import logger


class FirmsruScraper(BaseScraper):
    """Скрепер firmsru.ru через Playwright. Страница передаётся извне."""

    def __init__(self, config: dict, city: str, playwright_page=None):
        super().__init__(config, city)
        self.page = playwright_page
        self.source_config = config.get("sources", {}).get("firmsru", {})
        self.base_path = self.source_config.get("base_path", "/{city}/izgotovlenie-pamyatnikov/")

    def _build_url(self) -> str:
        """Строим URL для города с транслитерацией."""
        from utils import slugify
        city_slug = slugify(self.city)
        path = self.base_path.replace("{city}", city_slug)
        return f"https://firmsru.ru{path}"

    def scrape(self) -> list[RawCompany]:
        if not self.page:
            logger.warning("  Firmsru: Playwright page не передан, пропуск")
            return []

        companies = []
        url = self._build_url()
        logger.info(f"  Firmsru: {url}")

        try:
            self.page.goto(url, timeout=30000, wait_until="domcontentloaded")
            self.page.wait_for_load_state("domcontentloaded", timeout=20000)

            for _ in range(5):
                self.page.evaluate("window.scrollBy(0, 1000)")
                adaptive_delay(0.5, 1.0)

            cards = self.page.query_selector_all(
                "div.company, div.firm-item, a[href*='/firm/']"
            )

            for card in cards:
                try:
                    name_elem = card.query_selector("h3 a, h2 a, a.name, span.name")
                    if not name_elem:
                        continue
                    name = name_elem.inner_text().strip()
                    if not name or len(name) < 3:
                        continue

                    addr_elem = card.query_selector("address, div.address, span.address")
                    address = addr_elem.inner_text().strip() if addr_elem else ""

                    phone_elems = card.query_selector_all(
                        "span.phone, div.phone, a[href^='tel:']"
                    )
                    phones_raw = [pe.inner_text() for pe in phone_elems]
                    phones = normalize_phones(phones_raw)

                    site_elem = card.query_selector(
                        "a[href*='http']:not([href*='firmsru'])"
                    )
                    website = site_elem.get_attribute("href") if site_elem else None

                    page_content = card.inner_html()
                    emails = extract_emails(page_content)

                    messengers: dict = {}
                    for a_tag in card.query_selector_all("a[href*='t.me'], a[href*='vk.com']"):
                        href = a_tag.get_attribute("href") or ""
                        if "t.me" in href:
                            messengers["telegram"] = href
                        elif "vk.com" in href:
                            messengers["vk"] = href

                    companies.append(RawCompany(
                        source=Source.FIRMSRU,
                        source_url=url,
                        name=name,
                        phones=phones,
                        address_raw=address,
                        website=website,
                        emails=emails,
                        city=self.city,
                        messengers=messengers,
                    ))
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"  Firmsru error: {e}")

        return companies
