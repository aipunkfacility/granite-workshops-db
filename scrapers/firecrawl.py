# scrapers/firecrawl.py — рефакторинг scripts/firecrawl_granite.py
import subprocess
import json
import re
from scrapers.base import BaseScraper
from models import RawCompany, Source
from utils import normalize_phones, extract_emails, extract_domain
from loguru import logger
from database import Database


class FirecrawlScraper(BaseScraper):
    """Скрепер через firecrawl-cli (npx). Детальный сбор с сайтов."""

    def __init__(self, config: dict, city: str, db: Database):
        super().__init__(config, city)
        self.db = db
        self.source_config = config.get("sources", {}).get("firecrawl", {})
        self.queries = self.source_config.get("queries", [])
        self.limit = self.source_config.get("limit_per_query", 10)
        self.detail_limit = self.source_config.get("detail_scrape_limit", 10)

    def _run_firecrawl(self, args: list) -> str:
        """Запуск firecrawl-cli. Пробует разные команды для Windows/Linux."""
        # Список возможных команд (Windows npx.cmd, глобальный firecrawl и т.д.)
        commands_to_try = [
            ["firecrawl"] + args,
            ["npx.cmd", "-y", "firecrawl-cli@latest"] + args,
            ["npx", "-y", "firecrawl-cli@latest"] + args,
        ]
        
        last_error = ""
        for cmd in commands_to_try:
            try:
                # На Windows часто вывод в CP1251 или CP866, поэтому используем errors='replace'
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True,
                    encoding="utf-8", 
                    errors="replace",
                    timeout=120, 
                    shell=True
                )
                # Если команда выполнилась (даже если пустой выход, но без FileNotFoundError)
                return (result.stdout or "") + (result.stderr or "")
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                last_error = str(e)
                continue
                
        logger.error(f"  Firecrawl: не удалось запустить CLI. Ошибка: {last_error}")
        return ""

    def scrape(self) -> list[RawCompany]:
        companies = []
        for query in self.queries:
            search_query = f"{query} {self.city}"
            logger.info(f"  Firecrawl поиск: {search_query}")

            output = self._run_firecrawl([
                "search", search_query, "--limit", str(self.limit)
            ])

            found = self._parse_search_results(output)
            companies.extend(found)

        # Детальный сбор (первые N уникальных сайтов)
        seen_domains = set()
        detail_count = 0
        for company in companies:
            if detail_count >= self.detail_limit:
                break
            if not company.website:
                continue
            domain = extract_domain(company.website)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)

            logger.info(f"  [{detail_count+1}/{self.detail_limit}] Scrape: {company.website}")
            details = self._scrape_details(company.website)
            company.phones = normalize_phones(company.phones + details.get("phones", []))
            company.emails = list(set(company.emails + details.get("emails", [])))
            if not company.address_raw and details.get("addresses"):
                company.address_raw = details["addresses"][0]
            # Сохраняем промежуточный результат (checkpoint)
            self._save_checkpoint(company)
            detail_count += 1

        return companies

    def _parse_search_results(self, output: str) -> list[RawCompany]:
        """Парсинг вывода firecrawl search."""
        results = []
        lines = output.split("\n")
        current: dict = {}

        for line in lines:
            line = line.strip()
            if line.startswith("URL:"):
                url = line.replace("URL:", "").strip()
                if url:
                    current["url"] = url
            elif line and "http" not in line and not line.startswith("["):
                if len(line) > 3:
                    current["name"] = line

            if current.get("url") and current.get("name"):
                if not any(c.website == current["url"] for c in results):
                    results.append(RawCompany(
                        source=Source.FIRECRAWL,
                        source_url=current.get("url", ""),
                        name=current.get("name", ""),
                        phones=[],
                        address_raw="",
                        website=current.get("url"),
                        emails=[],
                        city=self.city,
                    ))
                current = {}

        return results

    def _scrape_details(self, url: str) -> dict:
        """Детальный скрапинг сайта через firecrawl."""
        output = self._run_firecrawl(["scrape", url, "--format", "markdown"])

        data: dict = {"phones": [], "emails": [], "addresses": []}

        phones = re.findall(
            r"(\+?7[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2})",
            output
        )
        data["phones"] = phones
        data["emails"] = extract_emails(output)

        address_patterns = [
            r"г\.?\s+[А-Яа-яё]+\s*,?\s*ул\.?\s+[А-Яа-яё]+",
            r"г\.?\s+[А-Яа-яё]+\s*,?\s*[А-Яа-яё]+\s+\d+",
        ]
        for pattern in address_patterns:
            data["addresses"].extend(re.findall(pattern, output))

        return data

    def _save_checkpoint(self, company: RawCompany):
        """Промежуточное сохранение в SQLite."""
        session = self.db.get_session()
        try:
            from database import RawCompanyRow
            row = RawCompanyRow(
                source=company.source.value,
                source_url=company.source_url,
                name=company.name,
                phones=company.phones,
                address_raw=company.address_raw,
                website=company.website,
                emails=company.emails,
                scraped_at=company.scraped_at,
                city=company.city,
            )
            session.add(row)
            session.commit()
        except Exception as e:
            logger.error(f"Checkpoint error: {e}")
            session.rollback()
        finally:
            session.close()
