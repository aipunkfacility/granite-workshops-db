# enrichers/network_detector.py
from database import Database, EnrichedCompanyRow
from loguru import logger
from utils import extract_domain

class NetworkDetector:
    """Выявляет сети (филиалы в разных городах)."""

    def __init__(self, db: Database):
        self.db = db

    def scan_for_networks(self, threshold: int = 2) -> None:
        """Пересчитывает флаг is_network для всех компаний в EnrichedCompanyRow.
        
        Если домен встречается в базе > threshold раз, это сеть.
        Если один и тот же телефон встречается в разных городах — это сеть.
        """
        session = self.db.get_session()
        try:
            # Сбрасываем флаги
            session.query(EnrichedCompanyRow).update({EnrichedCompanyRow.is_network: False})
            
            # Поиск сетей по домену
            all_companies = session.query(EnrichedCompanyRow).all()
            
            domain_count = {}
            for c in all_companies:
                domain = extract_domain(c.website)
                if domain:
                    domain_count[domain] = domain_count.get(domain, 0) + 1
                    
            network_domains = {d for d, c in domain_count.items() if c >= threshold}
            
            # Поиск сетей по телефону в РАЗНЫХ городах
            phone_cities = {}
            for c in all_companies:
                for p in c.phones:
                    if p:
                        if p not in phone_cities:
                            phone_cities[p] = set()
                        phone_cities[p].add(c.city.lower() if c.city else "")
                        
            network_phones = {p for p, cities in phone_cities.items() if len(cities) >= threshold}
            
            # Применяем флаги
            update_count = 0
            for c in all_companies:
                domain = extract_domain(c.website)
                is_net = False
                
                if domain in network_domains:
                    is_net = True
                else:
                    for p in c.phones:
                        if p in network_phones:
                            is_net = True
                            break
                            
                if is_net:
                    c.is_network = True
                    update_count += 1
                    
            session.commit()
            logger.info(f"Обнаружено {update_count} филиалов сетей.")
            
        except Exception as e:
            logger.error(f"NetworkDetector error: {e}")
            session.rollback()
        finally:
            session.close()
