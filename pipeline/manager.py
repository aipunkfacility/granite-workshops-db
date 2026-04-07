# pipeline/manager.py
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from dedup.site_matcher import cluster_by_site
from dedup.merger import merge_cluster
from dedup.validator import validate_phones, validate_emails, validate_website

# Import Enrichers
from enrichers.messenger_scanner import MessengerScanner
from enrichers.tech_extractor import TechExtractor
from enrichers.tg_finder import find_tg_by_phone, find_tg_by_name
from enrichers.tg_trust import check_tg_trust
from enrichers.classifier import Classifier
from enrichers.network_detector import NetworkDetector
from exporters.csv import CsvExporter
from exporters.markdown import MarkdownExporter
from regions import get_region_cities
from category_finder import discover_categories, get_categories, get_subdomain


class PipelineManager:
    """Управление основным циклом обогащения."""
    
    def __init__(self, config: dict, db: Database):
        self.config = config
        self.db = db
        self.checkpoints = CheckpointManager(db)
        self.classifier = Classifier(config)

    def _get_region_cities(self, city: str) -> list[str]:
        """Найти все города для этой области.
        
        Берёт область из config.yaml по названию города,
        затем подтягивает полный список городов из data/regions.yaml.
        
        Пример: city="Ростов-на-Дону" → region="Ростовская область" →
        ["Азов", "Аксай", "Батайск", ..., "Ростов-на-Дону", ..., "Шахты"]
        """
        target_region = None
        for c in self.config.get("cities", []):
            if c["name"] == city:
                target_region = c.get("region", "")
                break
        if not target_region:
            return [city]
        
        # Полный список городов из статичного файла
        region_file_cities = get_region_cities(target_region)
        if region_file_cities:
            return region_file_cities
        
        # Фоллбэк: города из config.yaml с той же областью
        siblings = []
        for c in self.config.get("cities", []):
            if c.get("region") == target_region:
                siblings.append(c["name"])
        return siblings if siblings else [city]

    def run_city(self, city: str, force: bool = False, run_scrapers: bool = True, re_enrich: bool = False):
        """Запуск полного цикла для города (и всех городов этой же области)."""
        print_status(f"Запуск конвейера для: {city}", "bold")
        
        region_cities = self._get_region_cities(city)
        if len(region_cities) > 1:
            print_status(f"Область включает города: {', '.join(region_cities)}", "info")
        
        if force:
            print_status("Флаг --force: очистка старых данных...", "warning")
            self.checkpoints.clear_city(city)
            
        # --re-enrich: перескакиваем на обогащение, не трогаем scrape/dedup/enriched
        
        stage = self.checkpoints.get_stage(city)
        print_status(f"Определен этап старта: {stage}")
        
        if re_enrich:
            # Пропускаем scrape+dedup, запускаем только точечный поиск (проход 2)
            self._run_phase_deep_enrich_existing(city)
        else:
            if stage == "start" and run_scrapers:
                self._run_phase_scrape(city, region_cities)
                stage = "scraped"
                
            if stage == "scraped":
                self._run_phase_dedup(city)
                stage = "deduped"
                
            if stage == "deduped":
                self._run_phase_enrich(city)
            
        # Пересчёт сетей только для текущего города/области
        print_status("Проверка филиальных сетей...", "info")
        net_det = NetworkDetector(self.db)
        net_det.scan_for_networks(threshold=2, city=city)
        
        # Пересчет скоринга (т.к. мы обновили is_network)
        self._recalc_scoring(city)

        # Автоэкспорт
        self._auto_export(city)
            
        print_status(f"Город {city} завершен!", "success")

    def _is_enabled(self, source: str) -> bool:
        """Проверить включён ли источник в config.yaml."""
        return self.config.get("sources", {}).get(source, {}).get("enabled", True)

    def _scrape_single_city(self, rc: str, city: str, cat_cache: dict) -> list:
        """Скрапинг одного города (для ThreadPoolExecutor)."""
        print_status(f"  Парсинг: {rc}", "info")
        city_results = []
        
        jsprav_cats = get_categories(cat_cache, "jsprav", rc)
        jsprav_sub = get_subdomain(cat_cache, "jsprav", rc, self.config)
        yell_cats = get_categories(cat_cache, "yell", rc)
        firmsru_cats = get_categories(cat_cache, "firmsru", rc)
        
        # 1. Быстрые скреперы (без Playwright)
        if self._is_enabled("jsprav"):
            jsprav = JspravScraper(self.config, rc, categories=jsprav_cats, subdomain=jsprav_sub)
            city_results.extend(jsprav.run())
        
        if self._is_enabled("firecrawl"):
            firecrawl = FirecrawlScraper(self.config, rc, self.db)
            city_results.extend(firecrawl.run())

        # 2. Playwright скреперы (NOT parallelizable — shared browser session)
        if self._is_enabled("dgis") or self._is_enabled("yell") or self._is_enabled("firmsru") or self._is_enabled("jsprav_playwright"):
            with playwright_session(headless=True) as (browser, page):
                if page:
                    if self._is_enabled("dgis"):
                        dgis = DgisScraper(self.config, rc, page)
                        city_results.extend(dgis.run())
                    if self._is_enabled("yell"):
                        yell = YellScraper(self.config, rc, page, categories=yell_cats)
                        city_results.extend(yell.run())
                    if self._is_enabled("firmsru"):
                        firmsru = FirmsruScraper(self.config, rc, page, categories=firmsru_cats)
                        city_results.extend(firmsru.run())
        
        return city_results

    def _run_phase_scrape(self, city: str, region_cities: list[str] = None):
        """ФАЗА 0+1: Поиск категорий и сбор данных."""
        if not region_cities:
            region_cities = [city]
        
        # Показываем какие источники включены
        active = [s for s in ["jsprav", "firecrawl", "dgis", "yell", "firmsru"] if self._is_enabled(s)]
        print_status(f"Источники: {', '.join(active)}", "info")
        
        # ФАЗА 0: Поиск рабочих категорий в справочниках
        if self._is_enabled("jsprav"):
            print_status("Поиск категорий в справочниках...", "info")
            cat_cache = discover_categories(region_cities, self.config)
        else:
            cat_cache = {}
        
        # ФАЗА 1: Сбор данных
        max_threads = self.config.get("scraping", {}).get("max_threads", 1)
        print_status(f"ФАЗА 1: Сбор данных (Scraping, threads={max_threads})", "info")
        
        raw_results = []
        
        if max_threads > 1 and len(region_cities) > 1:
            # Параллельный парсинг городов (только быстрые скреперы без Playwright)
            print_status(f"Параллельный парсинг {len(region_cities)} городов на {max_threads} потоках", "info")
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                future_to_city = {
                    executor.submit(self._scrape_single_city, rc, city, cat_cache): rc
                    for rc in region_cities
                }
                for future in as_completed(future_to_city):
                    rc = future_to_city[future]
                    try:
                        city_results = future.result()
                        raw_results.extend(city_results)
                        print_status(f"  {rc}: +{len(city_results)} записей", "success")
                    except Exception as e:
                        logger.error(f"  {rc}: ошибка парсинга — {e}")
                        print_status(f"  {rc}: ошибка — {e}", "warning")
        else:
            # Последовательный парсинг
            for rc in region_cities:
                try:
                    city_results = self._scrape_single_city(rc, city, cat_cache)
                    raw_results.extend(city_results)
                    print_status(f"  {rc}: +{len(city_results)} записей", "success")
                except Exception as e:
                    logger.error(f"  {rc}: ошибка парсинга — {e}")
                    print_status(f"  {rc}: ошибка — {e}", "warning")

        # Все результаты сохраняем под одним city — вся область вместе
        for r in raw_results:
            r.city = city
                
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
            raise
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
            dicts = []
            for r in raw_records:
                d = {
                    "id": r.id,
                    "source": r.source,
                    "source_url": r.source_url or "",
                    "name": r.name,
                    "phones": r.phones or [],
                    "address_raw": r.address_raw or "",
                    "website": r.website,
                    "emails": r.emails or [],
                    "geo": r.geo,
                    "messengers": r.messengers or {},
                    "city": r.city,
                }
                dicts.append(d)
            
            # Валидация перед кластеризацией
            for d in dicts:
                d["phones"] = validate_phones(d.get("phones", []))
                d["emails"] = validate_emails(d.get("emails", []))
            
            # Алгоритмы кластеризации (только телефон и сайт — без name_matcher)
            clusters_phone = cluster_by_phones(dicts)
            clusters_site = cluster_by_site(dicts)
            
            # Объединение всех кластеров (Union-Find)
            id_to_supercluster = {}
            for cid in [d["id"] for d in dicts]:
                id_to_supercluster[cid] = {cid}
                
            for cl in clusters_phone + clusters_site:
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
                    name_best=merged["name_best"],
                    phones=merged["phones"],
                    address=merged["address"],
                    website=merged["website"],
                    emails=merged["emails"],
                    city=merged["city"],
                    status="raw",
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
                logger.warning(f"Конфликты при слиянии: {len(conflicts)} компаний")
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка дедупликации для {city}: {e}")
            raise
        finally:
            session.close()

    def _run_phase_enrich(self, city: str, only_new: bool = False):
        """Обогащение данных. Если only_new=True — только компании без enriched-записи."""
        print_status("ФАЗА 3: Обогащение данных (Enrichment)", "info")
        session = self.db.get_session()
        try:
            if only_new:
                # Только те, у кого ещё нет enriched-записи
                enriched_ids = {
                    r[0] for r in
                    session.query(EnrichedCompanyRow.id).filter_by(city=city).all()
                }
                companies = [
                    c for c in session.query(CompanyRow).filter_by(city=city).all()
                    if c.id not in enriched_ids
                ]
                if not companies:
                    print_status("Нет новых компаний для обогащения", "info")
                    return
                print_status(f"Новых компаний: {len(companies)} (всего enriched: {len(enriched_ids)})", "info")
            else:
                companies = session.query(CompanyRow).filter_by(city=city).all()

            scanner = MessengerScanner(self.config)
            tech_ext = TechExtractor(self.config)
            
            count = 0
            for c in companies:
                # Скопировать базовые данные
                erow = EnrichedCompanyRow(
                    id=c.id,  # 1:1 связь
                    name=c.name_best,
                    phones=c.phones,
                    address_raw=c.address,
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
                        tg = find_tg_by_name(c.name_best, c.phones[0] if c.phones else None, self.config)
                        if tg:
                            messengers["telegram"] = tg
                            
                # 3. Анализ Telegram (Траст)
                tg_trust = {}
                if "telegram" in messengers:
                    tg_trust = check_tg_trust(messengers["telegram"])
                    
                erow.messengers = messengers
                erow.tg_trust = tg_trust
                
                session.merge(erow)
                count += 1
                # Показываем что именно делаем для каждой компании
                parts = []
                if erow.messengers:
                    parts.append(f"мессенджеры: {', '.join(erow.messengers.keys())}")
                if erow.cms:
                    parts.append(f"cms: {erow.cms}")
                detail = " | ".join(parts) if parts else "нет данных"
                print_status(f"Обогащено: {count}/{len(companies)} — {c.name_best} ({detail})")
                if count % 10 == 0:
                    session.commit()
                    
            session.commit()
            print_status(f"Обогащение завершено для {count} компаний", "success")

            # ── ПРОХОД 2: точечный поиск недостающих данных через firecrawl ──
            self._run_phase_deep_enrich(session, companies, city, scanner, tech_ext)

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка обогащения для {city}: {e}")
            raise
        finally:
            session.close()

    def _run_phase_deep_enrich(self, session, companies: list, city: str,
                                scanner, tech_ext):
        """Второй проход: для компаний без сайта/email — ищем через firecrawl."""
        # Фильтруем: нет сайта ИЛИ нет email
        needs_deep = []
        for c in companies:
            has_site = bool(c.website)
            has_email = bool(c.emails and len(c.emails) > 0)
            if not has_site or not has_email:
                needs_deep.append(c)

        if not needs_deep:
            print_status("Все компании уже с сайтами/email — точечный поиск не нужен", "info")
            return

        print_status(f"Точечный поиск: {len(needs_deep)} компаний без сайта или email", "info")

        if not self._is_enabled("firecrawl"):
            print_status("Firecrawl отключён — точечный поиск пропущен", "warning")
            return

        found = 0
        for c in needs_deep:
            erow = session.query(EnrichedCompanyRow).get(c.id)
            if not erow:
                continue

            # Формируем запрос: "Название Город"
            query = f"{c.name_best} {city}"
            logger.info(f"  Firecrawl поиск: {query}")

            result = self._firecrawl_search(query)
            if not result:
                continue

            web_results = result.get("data", {}).get("web", [])
            if not web_results:
                continue

            # Берём первый релевантный результат
            best_url = web_results[0].get("url", "")
            if not best_url:
                continue

            logger.info(f"  Найден сайт: {best_url} для {c.name_best}")

            # Скрапим сайт
            details = self._firecrawl_scrape(best_url)
            if not details:
                continue

            updated = []
            new_emails = details.get("emails", [])

            # Обновляем enriched-запись
            if not erow.website and best_url:
                erow.website = best_url
                updated.append("website")
                # Также обновляем companies
                c.website = best_url

            if new_emails:
                existing = set(erow.emails or [])
                for e in new_emails:
                    if e not in existing:
                        existing.add(e)
                        updated.append("email")
                erow.emails = list(existing)
                c.emails = list(existing)

            # Ищем мессенджеры на найденном сайте
            if best_url:
                valid_url, status = validate_website(best_url)
                if valid_url and status == 200:
                    site_messengers = scanner.scan_website(valid_url)
                    existing_msg = dict(erow.messengers or {})
                    for k, v in site_messengers.items():
                        if k not in existing_msg:
                            existing_msg[k] = v
                            updated.append(k)
                    erow.messengers = existing_msg

                    # CMS
                    if erow.cms in (None, "unknown", ""):
                        tech = tech_ext.extract(valid_url)
                        if tech.get("cms") and tech["cms"] != "unknown":
                            erow.cms = tech["cms"]
                            updated.append(f"cms:{tech['cms']}")

            if updated:
                found += 1
                logger.info(f"  ✓ {c.name_best}: добавлено {', '.join(updated)}")
            else:
                logger.debug(f"  — {c.name_best}: ничего нового не найдено")

            if found % 5 == 0:
                session.commit()

        session.commit()
        print_status(f"Точечный поиск: дополнено {found}/{len(needs_deep)} компаний", "success")

    def _run_phase_deep_enrich_existing(self, city: str):
        """Точечный поиск для уже обогащённых компаний: заполняет пустые website/email."""
        import time
        print_status("Точечный поиск недостающих данных (существующие компании)", "info")
        session = self.db.get_session()
        try:
            from enrichers.messenger_scanner import MessengerScanner
            from enrichers.tech_extractor import TechExtractor
            scanner = MessengerScanner(self.config)
            tech_ext = TechExtractor(self.config)

            # Берём enriched-записи где нет сайта ИЛИ нет email
            all_enriched = session.query(EnrichedCompanyRow).filter_by(city=city).all()
            needs_deep = [
                e for e in all_enriched
                if not e.website or not e.emails or len(e.emails) == 0
            ]

            if not needs_deep:
                print_status("Все компании уже с сайтами/email — нечего дополнять", "info")
                return

            print_status(f"Компаний для точечного поиска: {len(needs_deep)}/{len(all_enriched)}", "info")

            if not self._is_enabled("firecrawl"):
                print_status("Firecrawl отключён — точечный поиск пропущен", "warning")
                return

            found = 0
            no_result = 0
            for i, erow in enumerate(needs_deep, 1):
                c = session.query(CompanyRow).get(erow.id)
                if not c:
                    continue

                query = f"{erow.name} {city}"
                logger.info(f"  [{i}/{len(needs_deep)}] Firecrawl поиск: {query}")

                result = self._firecrawl_search(query)
                if not result:
                    no_result += 1
                    if no_result == 1:
                        logger.warning(f"  Пустой ответ для '{query}' — проверьте firecrawl CLI")
                    time.sleep(2)  # пауза даже при пустом ответе
                    continue

                web_results = result.get("data", {}).get("web", [])
                if not web_results:
                    no_result += 1
                    logger.debug(f"  Нет web-результатов для '{query}'")
                    time.sleep(2)
                    continue

                # Ищем наиболее релевантный URL: совпадение названия
                best_url = None
                for wr in web_results:
                    wr_url = wr.get("url", "")
                    wr_title = wr.get("title", "").lower()
                    if wr_url:
                        # Приоритет: если название компании есть в title
                        name_words = erow.name.lower().split()[:3]
                        if any(w in wr_title for w in name_words if len(w) > 2):
                            best_url = wr_url
                            break
                # Фоллбэк: первый результат
                if not best_url:
                    best_url = web_results[0].get("url", "")

                if not best_url:
                    time.sleep(2)
                    continue

                logger.info(f"  Найден сайт: {best_url} для {erow.name}")

                # Скрапим найденный сайт
                details = self._firecrawl_scrape(best_url)
                if not details:
                    logger.debug(f"  Скрапинг не дал данных для {best_url}")
                    time.sleep(2)
                    continue

                updated = []
                new_emails = details.get("emails", [])
                new_phones = details.get("phones", [])

                # Обновляем website
                if not erow.website and best_url:
                    erow.website = best_url
                    c.website = best_url
                    updated.append("website")

                # Обновляем email
                if new_emails:
                    existing = set(erow.emails or [])
                    for em in new_emails:
                        if em not in existing:
                            existing.add(em)
                            updated.append("email")
                    erow.emails = list(existing)
                    c.emails = list(existing)

                # Обновляем телефоны (дополняем)
                if new_phones:
                    existing_phones = set(erow.phones or [])
                    for ph in new_phones:
                        ph_norm = ph.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
                        if ph_norm not in existing_phones:
                            existing_phones.add(ph_norm)
                            updated.append("phone")
                    erow.phones = list(existing_phones)
                    c.phones = list(existing_phones)

                # Мессенджеры и CMS с найденного сайта
                if best_url:
                    valid_url, status = validate_website(best_url)
                    if valid_url and status == 200:
                        site_messengers = scanner.scan_website(valid_url)
                        existing_msg = dict(erow.messengers or {})
                        for k, v in site_messengers.items():
                            if k not in existing_msg:
                                existing_msg[k] = v
                                updated.append(k)
                        erow.messengers = existing_msg

                        if erow.cms in (None, "unknown", ""):
                            tech = tech_ext.extract(valid_url)
                            if tech.get("cms") and tech["cms"] != "unknown":
                                erow.cms = tech["cms"]
                                updated.append(f"cms:{tech['cms']}")

                if updated:
                    found += 1
                    logger.info(f"  ✓ {erow.name}: добавлено {', '.join(updated)}")

                # Пауза между запросами (2 сек)
                time.sleep(2)

                if found % 5 == 0:
                    session.commit()

            session.commit()
            print_status(f"Точечный поиск: дополнено {found}/{len(needs_deep)} компаний", "success")
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка точечного поиска: {e}")
        finally:
            session.close()

    def _firecrawl_search(self, query: str) -> dict | None:
        """Поиск через firecrawl CLI. Парсит stdout (JSON) или outfile."""
        import subprocess, json, os, tempfile, time
        try:
            result = subprocess.run(
                ["firecrawl", "search", query, "--limit", "3"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=60,
            )
            # При первой ошибке в сессии логируем stderr для отладки
            if result.returncode != 0 and result.stderr:
                logger.warning(f"Firecrawl search stderr (rc={result.returncode}): {result.stderr.strip()[:300]}")
                return None

            # Парсим stdout как JSON
            stdout = result.stdout.strip()
            if stdout:
                try:
                    return json.loads(stdout)
                except json.JSONDecodeError:
                    # Возможно JSON встроен в текстовый вывод — ищем { ... }
                    import re as _re
                    m = _re.search(r'\{.*\}', stdout, _re.DOTALL)
                    if m:
                        try:
                            return json.loads(m.group())
                        except json.JSONDecodeError:
                            pass
                    logger.debug(f"Firecrawl search: не удалось распарсить stdout ({len(stdout)} символов)")
            return None
        except subprocess.TimeoutExpired:
            logger.warning(f"Firecrawl search таймаут: {query[:60]}")
            return None
        except FileNotFoundError:
            logger.error("firecrawl CLI не найден — установите firecrawl-cli")
            return None
        except Exception as e:
            logger.debug(f"Firecrawl search ошибка: {e}")
            return None

    def _firecrawl_scrape(self, url: str) -> dict | None:
        """Скрапинг через firecrawl CLI. Парсит stdout (JSON) или outfile."""
        import subprocess, json, os, tempfile, re, time
        try:
            result = subprocess.run(
                ["firecrawl", "scrape", url, "--format", "markdown"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=60,
            )
            if result.returncode != 0 and result.stderr:
                logger.warning(f"Firecrawl scrape stderr (rc={result.returncode}): {result.stderr.strip()[:300]}")
                return None

            stdout = result.stdout.strip()
            if not stdout:
                return None

            # Пробуем распарсить как JSON
            data = None
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                # Возможно JSON встроен в текстовый вывод
                m = re.search(r'\{.*\}', stdout, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group())
                    except json.JSONDecodeError:
                        pass

            if not data:
                # Если не JSON — это может быть чистый markdown
                if len(stdout) > 50:
                    markdown = stdout
                else:
                    return None
            else:
                markdown = ""
                d = data.get("data", {})
                if isinstance(d, dict):
                    markdown = d.get("markdown", "") or d.get("html", "")
                elif isinstance(d, str):
                    markdown = d
                if not markdown:
                    return None

            from utils import extract_emails
            phones = re.findall(
                r"(\+?7[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2})",
                markdown,
            )
            return {"phones": phones, "emails": extract_emails(markdown)}
        except subprocess.TimeoutExpired:
            logger.warning(f"Firecrawl scrape таймаут: {url[:80]}")
            return None
        except FileNotFoundError:
            logger.error("firecrawl CLI не найден — установите firecrawl-cli")
            return None
        except Exception as e:
            logger.debug(f"Firecrawl scrape ошибка: {e}")
            return None
            
    def _recalc_scoring(self, city: str):
        """Пересчет скоринга и сегмента для обогащенных данных."""
        print_status("ФАЗА 5: Скоринг и сегментация", "info")
        session = self.db.get_session()
        try:
            companies = session.query(EnrichedCompanyRow).filter_by(city=city).all()
            if not companies:
                print_status("Нет данных для скоринга", "warning")
                return

            from collections import Counter
            segments = Counter()
            for c in companies:
                d = c.to_dict()
                score = self.classifier.calculate_score(d)
                segment = self.classifier.determine_segment(score, d)
                c.crm_score = score
                c.segment = segment
                segments[segment] += 1
            session.commit()

            summary = ", ".join(f"{seg}: {cnt}" for seg, cnt in sorted(segments.items()))
            print_status(f"Скоринг: {len(companies)} компаний → {summary}", "success")
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка пересчёта скоринга для {city}: {e}")
            raise
        finally:
            session.close()

    def _auto_export(self, city: str):
        """ФАЗА 6: Автоматический экспорт в CSV + пресеты."""
        print_status("ФАЗА 6: Экспорт CSV", "info")
        try:
            exporter = CsvExporter(self.db)
            exporter.export_city(city)
            print_status(f"Экспорт завершён: data/export/{city.lower()}_enriched.csv", "success")
        except Exception as e:
            logger.error(f"Ошибка экспорта для {city}: {e}")
            print_status(f"Экспорт не удался: {e}", "warning")

        # Экспорт пресетов из config.yaml
        export_presets = self.config.get("export_presets", {})
        if export_presets:
            print_status(f"Экспорт пресетов: {len(export_presets)} шт.", "info")
            for preset_name, preset in export_presets.items():
                try:
                    preset_format = preset.get("format", "csv")
                    if preset_format == "markdown" or preset_format == "md":
                        md_exporter = MarkdownExporter(self.db)
                        md_exporter.export_city_with_preset(city, preset_name, preset)
                    else:
                        csv_exporter = CsvExporter(self.db)
                        csv_exporter.export_city_with_preset(city, preset_name, preset)
                    print_status(f"  Пресет '{preset_name}': OK", "success")
                except Exception as e:
                    logger.error(f"Ошибка экспорта пресета '{preset_name}' для {city}: {e}")
                    print_status(f"  Пресет '{preset_name}': ошибка — {e}", "warning")
