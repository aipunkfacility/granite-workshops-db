# exporters/csv.py
import csv
import os
from database import Database, EnrichedCompanyRow
from loguru import logger

class CsvExporter:
    """Экспорт обогащенных данных в CSV."""

    def __init__(self, db: Database, output_dir: str = "data/export"):
        self.db = db
        self.output_dir = output_dir

    def export_city(self, city: str):
        """Экспорт одного города."""
        session = self.db.get_session()
        try:
            records = session.query(EnrichedCompanyRow).filter_by(city=city).all()
            if not records:
                logger.warning(f"Нет данных для экспорта {city}")
                return

            os.makedirs(self.output_dir, exist_ok=True)
            filepath = os.path.join(self.output_dir, f"{city.lower()}_enriched.csv")

            fields = [
                "id", "name", "phones", "address", "website", "emails",
                "segment", "crm_score", "is_network", "cms", "has_marquiz",
                "telegram", "vk", "whatsapp"
            ]

            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for r in sorted(records, key=lambda x: x.crm_score, reverse=True):
                    d = r.to_dict()
                    messengers = d.get("messengers", {})
                    writer.writerow({
                        "id": d["id"],
                        "name": d["name"],
                        "phones": "; ".join(d.get("phones", [])),
                        "address": d.get("address_raw", ""),
                        "website": d.get("website", ""),
                        "emails": "; ".join(d.get("emails", [])),
                        "segment": d.get("segment", ""),
                        "crm_score": d.get("crm_score", 0),
                        "is_network": "Yes" if d.get("is_network") else "No",
                        "cms": d.get("cms", ""),
                        "has_marquiz": "Yes" if d.get("has_marquiz") else "No",
                        "telegram": messengers.get("telegram", ""),
                        "vk": messengers.get("vk", ""),
                        "whatsapp": messengers.get("whatsapp", "")
                    })
            logger.info(f"Экспорт CSV завершен: {filepath}")
        finally:
            session.close()
