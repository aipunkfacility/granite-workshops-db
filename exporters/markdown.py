# exporters/markdown.py
import os
from database import Database, EnrichedCompanyRow
from loguru import logger

class MarkdownExporter:
    """Генератор Markdown-отчетов для Notion/Obsidian."""

    def __init__(self, db: Database, output_dir: str = "data/export"):
        self.db = db
        self.output_dir = output_dir

    def export_city(self, city: str):
        session = self.db.get_session()
        try:
            records = session.query(EnrichedCompanyRow).filter_by(city=city).all()
            if not records:
                return

            os.makedirs(self.output_dir, exist_ok=True)
            filepath = os.path.join(self.output_dir, f"{city.lower()}_report.md")

            # Группировка по сегментам
            segments = {"A": [], "B": [], "C": [], "D": []}
            for r in records:
                seg = r.segment or "D"
                if seg in segments:
                    segments[seg].append(r)
                else:
                    segments["D"].append(r)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# База мастерских: {city.capitalize()}\n\n")
                f.write(f"**Всего компаний:** {len(records)}\n\n")

                for seg in ["A", "B", "C", "D"]:
                    seg_records = segments[seg]
                    if not seg_records:
                        continue

                    f.write(f"## Сегмент {seg} ({len(seg_records)} шт.)\n\n")
                    f.write("| Название | Телефон | Сайт | Telegram | CMS | Score |\n")
                    f.write("|----------|---------|------|----------|-----|-------|\n")

                    for r in sorted(seg_records, key=lambda x: x.crm_score, reverse=True):
                        d = r.to_dict()
                        phones = "<br>".join(d.get("phones", []))
                        site = f"[Сайт]({d['website']})" if d.get("website") else "-"
                        
                        tg = d.get("messengers", {}).get("telegram")
                        tg_link = f"[TG]({tg})" if tg else "-"
                        
                        f.write(f"| **{d['name']}** | {phones} | {site} | {tg_link} | {d.get('cms', '-')} | {d.get('crm_score', 0)} |\n")
                    
                    f.write("\n")

            logger.info(f"Экспорт Markdown завершен: {filepath}")
        finally:
            session.close()
