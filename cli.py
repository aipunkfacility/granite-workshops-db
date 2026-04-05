# cli.py
import typer
import yaml
from database import Database
from pipeline.manager import PipelineManager
from exporters.csv import CsvExporter
from exporters.markdown import MarkdownExporter
from pipeline.status import print_status

app = typer.Typer(help="Granite Workshops DB - Сбор и обогащение базы ритуальных мастерских")

def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

@app.command()
def run(
    city: str = typer.Argument(..., help="Название города, например 'Астрахань' или 'all' для всех"),
    force: bool = typer.Option(False, "--force", "-f", help="Очистить старые данные и начать заново"),
    no_scrape: bool = typer.Option(False, "--no-scrape", help="Пропустить фазу парсинга (использовать кэш)")
):
    """Запуск полного цикла сбора, дедупликации и обогащения для города."""
    config = load_config()
    db = Database(config["database"]["path"])
    
    manager = PipelineManager(config, db)
    
    target_cities = []
    if city.lower() == "all":
        target_cities = [c["name"] for c in config.get("cities", [])]
    else:
        target_cities = [city]
        
    for c in target_cities:
        manager.run_city(c, force=force, run_scrapers=not no_scrape)

@app.command()
def export(
    city: str = typer.Argument(..., help="Название города или 'all'"),
    format: str = typer.Option("csv", "--format", "-f", help="Формат экспорта: csv или md")
):
    """Экспорт готовых данных из БД."""
    config = load_config()
    db = Database(config["database"]["path"])
    
    target_cities = []
    if city.lower() == "all":
        target_cities = [c["name"] for c in config.get("cities", [])]
    else:
        target_cities = [city]

    for c in target_cities:
        if format == "csv":
            exporter = CsvExporter(db)
        else:
            exporter = MarkdownExporter(db)
        exporter.export_city(c)
        
    print_status("Экспорт завершен успешно!", "success")

if __name__ == "__main__":
    app()
