# pipeline/manager.py
from database import Database, RawCompanyRow, CompanyRow, EnrichedCompanyRow
from pipeline.checkpoint import CheckpointManager
from pipeline.status import print_status
from loguru import logger

# Import Scrapers
from scrapers._playwright import playwright_session
from scrapers.jsprav import JspravScraper
from scrapers.dgis import DgisScraper
from scrapers.yell import YellScraper
from scrapers.firmsru import FirmsruScraper
from scrapers.jsprav_playwright import JspravPlaywrightScraper
from scrapers.firecrawl import FirecrawlScraper

# Import Dedup
from dedup.phone_cluster import cluster_by_phones
from dedup.name_matcher import find_name_matches
from dedup.site_matcher import cluster_by_site
from dedup.merger import merge_cluster, generate_conflicts_md
from dedup.validator import validate_phones, validate_emails, validate_website

# Import Enrichers
from enrichers.messenger_scanner import MessengerScanner
from enrichers.tech_extractor import TechExtractor
from enrichers.tg_finder import find_tg_by_phone, find_tg_by_name
from enrichers.tg_trust import check_tg_trust
from enrichers.classifier import Classifier
from enrichers.network_detector import NetworkDetector


class PipelineManager:
    """Управление основным циклом обогащения."""
    
    def __init__(self, config: dict, db: Database):
        self.config = config
        self.db = db
        self.checkpoints = CheckpointManager(db)
        self.classifier = Classifier(config)

    def run_city(self, city: str, force: bool = False, run_scrapers: bool = True):
        """Запуск полного цикла для города."""
        print_status(f"Запуск конвейера для города: {city}", "bold")
        
        if force:
            print_status("Флаг --force: очистка старых данных...", "warning")
            self.checkpoints.clear_city(city)
            
        stage = self.checkpoints.get_stage(city)
        print_status(f"Определен этап старта: {stage}")
        
        if stage == "start" and run_scrapers:
            self._run_phase_scrape(city)
            stage = "scraped"
            
        if stage == "scraped":
            self._run_phase_dedup(city)
            stage = "deduped"
            
        if stage == "deduped":
            self._run_phase_enrich(city)
            
        # Общий пересчет сетей (Networks) всегда в конце
        print_status("Проверка филиальных сетей...", "info")
        net_det = NetworkDetector(self.db)
        net_det.scan_for_networks()
        
        # Пересчет скоринга (т.к. мы обновили is_network)
        self._recalc_scoring(city)
            
        print_status(f"Город {city} завершен!", "success")

    def _run_phase_scrape(self, city: str):
        print_status("ФАЗА 1: Сбор данных (Scraping)", "info")
        raw_results = []
        
        # 1. Быстрые скреперы (без Playwright)
        jsprav = JspravScraper(self.config, city)
        raw_results.extend(jsprav.run())
        
        firecrawl = FirecrawlScraper(self.config, city, self.db)
        raw_results.extend(firecrawl.run())

        # 2. Playwright скреперы
        print_status("Запуск Playwright (браузерных) скреперов...", "info")
        with playwright_session(headless=True) as (browser, page):
            if page:
                dgis = DgisScraper(self.config, city, page)
                yell = YellScraper(self.config, city, page)
                firmsru = FirmsruScraper(self.config, city, page)
                jsprav_pw = JspravPlaywrightScraper(self.config, city, page)
                
                raw_results.extend(dgis.run())
                raw_results.extend(yell.run())
                raw_results.extend(firmsru.run())
                raw_results.extend(jsprav_pw.run())
                
        # Сохранение сырых данных в БД
        session = self.db.get_session()
        try:
            for r in raw_results:
                row = RawCompanyRow(
                    source=r.source.value,
                    source_url=r.source_url,
                    name=r.name,
                    phones=r.phones,
                    address_raw=r.address_raw,
                    website=r.website,
                    emails=r.emails,
                    scraped_at=r.scraped_at,
                    city=r.city,
                    messengers=r.messengers
                )
                session.add(row)
            session.commit()
            print_status(f"Собрано {len(raw_results)} записей", "success")
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка сохранения сырых данных: {e}")
        finally:
            session.close()

    def _run_phase_dedup(self, city: str):
        """Фаза дедупликации сырых данных из БД."""
        print_status("ФАЗА 2: Дедупликация и слияние (Dedup)", "info")
        session = self.db.get_session()
        try:
            raw_records = session.query(RawCompanyRow).filter_by(city=city).all()
            if not raw_records:
                print_status("Нет данных для дедупликации", "warning")
                return
                
            # Перевод в dict для алгоритмов
            dicts = [r.to_dict() for r in raw_records]
            
            # Валидация перед кластеризацией
            for d in dicts:
                d["phones"] = validate_phones(d.get("phones", []))
                d["emails"] = validate_emails(d.get("emails", []))
            
            # Алгоритмы кластеризации
            clusters_phone = cluster_by_phones(dicts)
            clusters_site = cluster_by_site(dicts)
            
            threshold = self.config.get("dedup", {}).get("name_similarity_threshold", 88)
            clusters_name = find_name_matches(dicts, threshold)
            
            # Объединение всех кластеров (Union-Find)
            id_to_supercluster = {}
            for cid in [d["id"] for d in dicts]:
                id_to_supercluster[cid] = {cid}
                
            for cl in clusters_phone + clusters_site + clusters_name:
                connected = set()
                for cid in cl:
                    connected.update(id_to_supercluster[cid])
                for cid in connected:
                    id_to_supercluster[cid] = connected
                    
            # Уникальные суперкластеры
            seen = set()
            superclusters = []
            for cid, cl in id_to_supercluster.items():
                k = frozenset(cl)
                if k not in seen:
                    seen.add(k)
                    superclusters.append(list(cl))
                    
            print_status(f"Найдено {len(superclusters)} уникальных компаний из {len(dicts)} записей")
            
            conflicts = []
            
            # Слияние и сохранение
            for i, cl in enumerate(superclusters):
                cluster_dicts = [d for d in dicts if d["id"] in cl]
                merged = merge_cluster(cluster_dicts)
                
                # Сохраняем в БД
                row = CompanyRow(
                    name=merged["name_best"],
                    phones=merged["phones"],
                    address_raw=merged["address"],
                    website=merged["website"],
                    emails=merged["emails"],
                    city=merged["city"],
                    messengers=merged["messengers"],
                    needs_review=merged["needs_review"],
                    review_reason=merged["review_reason"],
                )
                session.add(row)
                
                # Если конфликт - в отчет
                if merged["needs_review"]:
                    conflicts.append({
                        "cluster_id": i+1,
                        "records": cluster_dicts,
                        "reason": merged["review_reason"]
                    })
                    
            session.commit()
            
            if conflicts:
                generate_conflicts_md(conflicts, city)
                print_status(f"Сформирован файл конфликтов для {len(conflicts)} компаний", "warning")
                
        finally:
            session.close()

    def _run_phase_enrich(self, city: str):
        """Обогащение данных."""
        print_status("ФАЗА 3: Обогащение данных (Enrichment)", "info")
        session = self.db.get_session()
        try:
            companies = session.query(CompanyRow).filter_by(city=city).all()
            scanner = MessengerScanner(self.config)
            tech_ext = TechExtractor(self.config)
            
            count = 0
            for c in companies:
                # Скопировать базовые данные
                erow = EnrichedCompanyRow(
                    id=c.id,  # 1:1 связь
                    name=c.name,
                    phones=c.phones,
                    address_raw=c.address_raw,
                    website=c.website,
                    emails=c.emails,
                    city=c.city,
                )
                
                messengers = dict(c.messengers) if c.messengers else {}
                
                # 1. Сканирование сайта
                if c.website:
                    valid_url, status = validate_website(c.website)
                    erow.website = valid_url  # Сохраняем нормализованный
                    if valid_url and status == 200:
                        site_messengers = scanner.scan_website(valid_url)
                        for k, v in site_messengers.items():
                            if k not in messengers:
                                messengers[k] = v
                                
                        tech = tech_ext.extract(valid_url)
                        erow.cms = tech["cms"]
                        erow.has_marquiz = tech["has_marquiz"]
                
                # 2. Поиск Telegram
                if "telegram" not in messengers:
                    # Сначала по телефону
                    if c.phones:
                        tg = find_tg_by_phone(c.phones[0], self.config)
                        if tg:
                            messengers["telegram"] = tg
                            
                    # Затем по названию
                    if "telegram" not in messengers:
                        tg = find_tg_by_name(c.name, c.phones[0] if c.phones else None, self.config)
                        if tg:
                            messengers["telegram"] = tg
                            
                # 3. Анализ Telegram (Траст)
                tg_trust = {}
                if "telegram" in messengers:
                    tg_trust = check_tg_trust(messengers["telegram"])
                    
                erow.messengers = messengers
                erow.tg_trust = tg_trust
                
                session.add(erow)
                count += 1
                if count % 10 == 0:
                    print_status(f"Обогащено: {count}/{len(companies)}")
                    session.commit()
                    
            session.commit()
            print_status(f"Обогащение завершено для {count} компаний", "success")
        finally:
            session.close()
            
    def _recalc_scoring(self, city: str):
        """Пересчет скоринга и сегмента для обогащенных данных."""
        session = self.db.get_session()
        try:
            companies = session.query(EnrichedCompanyRow).filter_by(city=city).all()
            for c in companies:
                d = c.to_dict()
                score = self.classifier.calculate_score(d)
                segment = self.classifier.determine_segment(score, d)
                c.crm_score = score
                c.segment = segment
            session.commit()
        finally:
            session.close()
