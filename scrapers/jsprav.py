# scrapers/jsprav.py — рефакторинг scripts/scrape_fast.py (JSON-LD, быстрая версия)
import requests
import json
import re
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper
from models import RawCompany, Source
from utils import normalize_phone, normalize_phones, extract_domain
from loguru import logger


class JspravScraper(BaseScraper):
    """Скрепер jsprav.ru через JSON-LD — быстрый, не требует Playwright."""

    def __init__(self, config: dict, city: str):
        super().__init__(config, city)
        self.source_config = config.get("sources", {}).get("jsprav", {})
        self.categories = self.source_config.get("categories", [
            "izgotovlenie-pamyatnikov",
            "pamyatniki-i-nadgrobiya",
        ])
        self.subdomain_map = self.source_config.get("subdomain_map", {})

    def _get_subdomain(self) -> str:
        """Определяем поддомен для города. Для нестандартных — берём из конфига."""
        city_lower = self.city.lower()
        if city_lower in self.subdomain_map:
            return self.subdomain_map[city_lower]
            
        from utils import slugify
        return slugify(self.city)

    def scrape(self) -> list[RawCompany]:
        companies = []
        subdomain = self._get_subdomain()

        for category in self.categories:
            page = 1
            max_pages = 10
            
            while page <= max_pages:
                base_dir = f"https://{subdomain}.jsprav.ru/{category}/"
                url = base_dir if page == 1 else f"{base_dir}?page={page}"
                logger.info(f"  JSprav: {url}")
                
                try:
                    r = requests.get(url, timeout=30,
                                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                    if r.status_code == 404:
                        if page == 1:
                            logger.warning(f"  JSprav: 404 для {url}")
                        break  # Дальше страниц нет
                        
                    soup = BeautifulSoup(r.text, "html.parser")
                    page_found = 0
                    
                    for script in soup.find_all("script", type="application/ld+json"):
                        try:
                            data = json.loads(script.string)
                            if data.get("@type") != "ItemList":
                                continue
                            for item in data.get("itemListElement", []):
                                c = item.get("item", {})
                                if c.get("@type") != "LocalBusiness":
                                    continue
                                name = c.get("name", "")
                                if not name:
                                    continue

                                addr = c.get("address", {})
                                same = c.get("sameAs", [])
                                phones = normalize_phones(c.get("telephone", []))
                                website = same[0] if same else None

                                geo = None
                                if c.get("geo"):
                                    try:
                                        lat = float(c["geo"].get("latitude", 0))
                                        lon = float(c["geo"].get("longitude", 0))
                                        if lat and lon:
                                            geo = (lat, lon)
                                    except (ValueError, TypeError):
                                        pass

                                companies.append(RawCompany(
                                    source=Source.JSPRAV,
                                    source_url=url,
                                    name=name,
                                    phones=phones,
                                    address_raw=f"{addr.get('streetAddress', '')}, "
                                                f"{addr.get('addressLocality', '')}".strip(", "),
                                    website=website,
                                    emails=[],
                                    city=self.city,
                                    geo=geo,
                                ))
                                page_found += 1
                        except (json.JSONDecodeError, KeyError, AttributeError):
                            continue
                    
                    if page_found == 0:
                        break # На этой странице не было JSON-LD с карточками, конец категории
                    
                    page += 1
                    import time
                    time.sleep(1.0) # Небольшая пауза между страницами
                    
                except Exception as e:
                    logger.error(f"  JSprav error ({category}, page {page}): {e}")
                    break

        logger.info(f"  JSprav: итого {len(companies)} компаний для {self.city}")
        return companies
