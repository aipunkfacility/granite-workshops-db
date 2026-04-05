# Гайд: Управление источниками (скреперами)

## 1. Источники в плане (зафиксировано)

### 1.1. Включены по умолчанию (`enabled: true`)

| Источник | Файл | Метод | Что даёт | Нюансы скрапинга |
|---|---|---|---|---|
| **JSprav** | `scrapers/jsprav.py` | JSON-LD (requests + BeautifulSoup) | Название, телефон, адрес, сайт, geo (lat/lon) | **Основной источник, ~50-150 компаний на город.** Данные в `<script type="application/ld+json">` — парсится быстро без Playwright. Нестандартные поддомены (astrahan→astrahan, moscow→moskva1, spb→sankt-peterburg1) — маппинг в `config.yaml → sources.jsprav.subdomain_map`. Файл `scrape_fast.py` в легаси закодирован в UTF-16 BOM — при рефакторинге пересохранить в UTF-8. Две категории: `ritualnyie-uslugi` и `ritualnyie-prinadlezhnosti-i-izgotovlenie-venkov`. |
| **2GIS** | `scrapers/dgis.py` | Playwright (headless Chromium) | Название, телефон, адрес, мессенджеры (VK/TG/IG прямо в карточке) | **Требует Playwright + stealth.** Динамический рендеринг — данные подгружаются JS. Карточки компаний через селекторы `div[class*='card'], div[class*='firm']`. Скролл 3× по 1000px для загрузки. URL: `https://{город}.2gis.ru/search/ритуальные услуги`. Часто показывает соцсети в карточке — сбор через `a[href*='vk.com'], a[href*='t.me']`. |
| **Yell.ru** | `scrapers/yell.py` | Playwright (headless Chromium) | Название, телефон, адрес, сайт, email | **Playwright обязательна.** URL: `https://{город}.yell.ru/catalog/ritualnye_uslugi/`. Селекторы нестабильны — `div.company-card, div.listing-item`. Скролл 5×. Сайты иногда спрятаны за внешние ссылки. |
| **Firmsru** | `scrapers/firmsru.py` | Playwright (headless Chromium) | Название, телефон, адрес, сайт, email | **Playwright обязательна.** URL: `https://firmsru.ru/{город}/ритуальные-услуги/`. Структура похожа на Yell. Селекторы: `div.company, div.firm-item`. Email часто есть в карточке. |
| **Firecrawl** | `scrapers/firecrawl.py` | CLI: `npx firecrawl-cli search/scrape` | Название, сайт, телефон, email, адрес | **Требует установленный Node.js + firecrawl-cli.** Двухэтапный: (1) поиск по запросам из config → список URL, (2) детальный scrape каждого URL → markdown → regex-экстракция. Даёт уникальные результаты, не пересекаясь с каталогами. Запросы: "гранитная мастерская памятники {город}" и 4 варианта. |

### 1.2. Отключены по умолчанию (`enabled: false`)

| Источник | Файл | Почему выключен | Что нужно для включения |
|---|---|---|---|
| **Google Maps** | `scrapers/google_maps.py` | Требует API-ключ или прокси для стабильной работы. Без прокси быстро банит. | Google Maps API (платный) или Selenium/Playwright с прокси. `max_retries: 5` (капризнее остальных). Реализация: Grid Search по координатам города (`geo_center` из config) с шагом `grid_step_km`. |
| **Avito** | `scrapers/avito.py` | Агрессивно банит. Частные мастера, много нерелевантных. | Прокси + частая смена UA. `max_retries: 2` — быстро банит, не стоит упорствовать. URL: `https://avito.ru/{город}/uslugi/ritualnye_uslugi`. |

---

## 2. Источники НЕ в плане, но потенциально полезные

### 2.1. Каталоги и справочники

| Источник | URL-шаблон | Тип | Сложность | Что даёт | Почему стоит рассмотреть |
|---|---|---|---|---|---|
| **Яндекс.Карты** | `https://yandex.ru/maps/{region}/?text=ритуальные+услуги` | Карта (Playwright) | ★★★☆☆ | Название, телефон, адрес, сайт, рейтинг, отзывы, часы работы | **Самый крупный источник в РФ после Google Maps.** Отличные рейтинги и отзывы — можно подтягивать `map_rating` и `map_reviews_count` напрямую. Но: сильная защита от ботов, нужны stealth + delays. |
| **Spravker.ru** | `https://spravker.ru/{город}/ritualnye-uslugi/` | Каталог (requests) | ★★☆☆☆ | Название, телефон, адрес, сайт | Упомянут в `directories.md`. Справочник с чистой HTML-структурой. Вероятно парсится без Playwright. Нужно проверить. |
| **Zoon.ru** | `https://zoon.ru/{город}/ritualnye_uslugi/` | Каталог (requests/Playwright) | ★★☆☆☆ | Название, телефон, адрес, сайт, рейтинг, отзывы | Крупный каталог услуг. Показывает рейтинг (можно мапить в `map_rating`). Структура стабильнее Yell. |
| **GdeUslugi.ru** | `https://gdeuslugi.ru/{город}/ritualnye-uslugi` | Каталог (requests) | ★☆☆☆☆ | Название, телефон, адрес | Мелкий каталог, но может дать уникальные записи в малых городах. |
| **Ritual.ru** | `https://ritual.ru/catalog/companies/` | Портал (Playwright) | ★★★☆☆ | Название, телефон, адрес, сайт | Профильный ритуальный портал. Но: национальный уровень, без привязки к конкретному городу (нужна фильтрация). Возможна пагинация через JS. |
| **Vse-Horoshi.ru** | `https://vse-horoshi.ru/ritual` | Справочник (requests) | ★★☆☆☆ | Название, телефон | Специализированный справочник. Малый охват, но в некоторых городах могут быть уникальные записи. |

### 2.2. Доски объявлений

| Источник | URL-шаблон | Сложность | Что даёт | Нюансы |
|---|---|---|---|---|
| **Юла (Youla)** | `https://youla.ru/{город}` | ★★☆☆☆ | Название, телефон (иногда), описание | Частные мастера. Много мусора. Нужно фильтровать по ключевым словам ("памятник", "гранит", "ритуал"). Юла объединена с Авито — можно не делать отдельно. |

### 2.3. Социальные сети (как источники компаний, не обогащения)

| Источник | Сложность | Что даёт | Нюансы |
|---|---|---|---|
| **VK поиск** | ★★★★☆ | Названия, телефоны, адреса, ссылки на сайты | Очень много мастерских имеют VK-группы. Можно искать по `https://vk.com/search?c[section]=communities&q=памятники {город}`. Но: VK агрессивно банит без авторизации. Нужен VK API token или Selenium с авторизацией. Не стоит делать в первой версии. |
| **Одноклассники** | ★★★☆☆ | Названия, телефоны | Популярны в малых городах (от 100к населения). OK API более лоялен к ботам. Низкий приоритет. |

### 2.4. Поисковики (мета-скрапинг, не API)

| Источник | Сложность | Что даёт | Нюансы |
|---|---|---|---|
| **Google поиск** | ★★★★☆ | Списки сайтов гранитных мастерских по городам | Аналогично Firecrawl, но бесплатно. URL: `https://www.google.com/search?q=гранитная мастерская памятники {город}`. Парсить `a[href]` из результатов. Google капчит после ~20 запросов. Уже используется в `tg_finder.py` (метод 2) — можно переиспользовать логику. |
| **Яндекс поиск** | ★★★☆☆ | Списки сайтов | Яндекс менее агрессивен, чем Google при поиске с одного IP. Можно использовать как альтернативу Firecrawl. |

---

## 3. Как добавить новый скрепер

### Шаг 1. Добавить значение в `Source` enum

```python
# models.py
class Source(str, Enum):
    # ... существующие
    ZOON = "zoon"           # ← новый
```

### Шаг 2. Добавить конфигурацию в `config.yaml`

```yaml
sources:
  zoon:
    enabled: true
    max_retries: 3
    base_path: "/{city}/ritualnye_uslugi/"
    # любые специфичные настройки
```

### Шаг 3. Создать файл `scrapers/zoon.py`

```python
# scrapers/zoon.py
from scrapers.base import BaseScraper
from models import RawCompany, Source
from utils import normalize_phones, extract_emails
from loguru import logger
from database import Database


class ZoonScraper(BaseScraper):
    """Парсер Zoon.ru для ритуальных услуг."""

    def __init__(self, config: dict, city: str, db: Database = None):
        super().__init__(config, city)
        self.db = db
        self.source_config = config.get("sources", {}).get("zoon", {})
        self.base_path = self.source_config.get("base_path", "")

    def scrape(self) -> list[RawCompany]:
        """Основной метод. Обязательный интерфейс BaseScraper."""
        companies = []
        # ... логика скрапинга ...
        return companies

    def _save_checkpoint(self, company: RawCompany):
        """Промежуточное сохранение в SQLite (опционально)."""
        if not self.db:
            return
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
                geo=f"{company.geo[0]},{company.geo[1]}" if company.geo else None,
                messengers=company.messengers,
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
```

### Шаг 4. Зарегистрировать в `pipeline/runner.py`

В функции `_get_scrapers()` (или эквиваленте) добавить импорт и инстанциацию:

```python
from scrapers.zoon import ZoonScraper

def _get_scrapers(self, config: dict, city: str, db: Database) -> list:
    scrapers = []
    sources_cfg = config.get("sources", {})

    for source_name, ScraperClass in [
        ("jsprav", JspravScraper),
        ("2gis", DgisScraper),
        ("yell", YellScraper),
        ("firmsru", FirmsruScraper),
        ("firecrawl", FirecrawlScraper),
        ("zoon", ZoonScraper),        # ← новый
    ]:
        source_cfg = sources_cfg.get(source_name, {})
        if not source_cfg.get("enabled", False):
            logger.info(f"  {source_name}: пропущен (enabled=false)")
            continue
        scrapers.append(ScraperClass(config, city, db))

    return scrapers
```

### Шаг 5. Написать тест (если есть тестируемая логика)

```python
# tests/test_zoon.py
# Только если в скрепере есть парсинг/нормализация, которую можно тестировать
# без сетевых запросов.
```

---

## 4. Как заменить существующий скрепер

### Сценарий: Yell.ru перестал работать, заменяем на Zoon.ru

**Шаг 1.** Отключить старый в `config.yaml`:

```yaml
sources:
  yell:
    enabled: false           # ← выключить
    # ... настройки остаются
```

**Шаг 2.** Создать новый скрепер `scrapers/zoon.py` (по инструкции выше).

**Шаг 3.** Добавить в `pipeline/runner.py` (по инструкции выше).

**Шаг 4.** Если новый скрепер даёт те же данные (название, телефон, адрес, сайт) — **ничего больше менять не нужно.** Дедупликатор автоматически:
- Сольёт дубли от Zoon с дубликатами от JSprav/2GIS по телефонам.
- Объединит мессенджеры из разных источников.
- Запишет в `companies` таблицу.

### Сценарий: Хочешь заменить JSprav (основной источник)

**Шаг 1.** Создать альтернативу `scrapers/jsprav_v2.py` с новым `Source.JSPRAV_V2`.

**Шаг 2.** Временно включить оба: `jsprav: enabled: true` и `jsprav_v2: enabled: true`.

**Шаг 3.** Запустить на тестовом городе. Сравнить результаты.

**Шаг 4.** Если V2 лучше — переключить: `jsprav: enabled: false`, `jsprav_v2: enabled: true`.

**Шаг 5.** Старый файл `scrapers/jsprav.py` не удалять — оставить в репозитории.

---

## 5. Принципы скрапинга (обязательные для всех источников)

### 5.1. Анти-блокировка

Все скреперы обязаны:
- Использовать `adaptive_delay(min=1.0, max=3.5)` из `utils.py` между запросами к одному домену.
- Для Playwright-скреперов — использовать `playwright_session()` из `_playwright.py` (включает stealth + рандомный UA).
- Прокси — **не используются** на текущем масштабе. Если источник банит без прокси — поставить `enabled: false` и добавить комментарий.

### 5.2. Обработка ошибок

- Все сетевые запросы через `fetch_page()` из `utils.py` (включает tenacity retry).
- `max_retries` берётся из `config.yaml → sources.{name}.max_retries`.
- При 403/404 — **не ретраить**. Это не временная ошибка, это блок или отсутствие страницы.
- При таймауте/502/503 — ретраить до `max_retries` раз с exponential backoff.

### 5.3. Формат выхода

Каждый скрепер обязан возвращать `list[RawCompany]`. Поля:

| Поле | Обязательное? | Что класть |
|---|---|---|
| `source` | Да | `Source.{ENUM_VALUE}` |
| `name` | Да | Название компании, cleaned |
| `phones` | Нет | `list[str]` в формате E.164 (через `normalize_phones()`) |
| `address_raw` | Нет | Адрес как есть на сайте |
| `website` | Нет | Полный URL |
| `emails` | Нет | `list[str]` |
| `geo` | Нет | `(lat, lon)` если есть |
| `messengers` | Нет | `dict` — `{"telegram": "...", "vk": "...", ...}` если видны в карточке |
| `source_url` | Да | URL страницы откуда взята запись |
| `city` | Да | Из параметра конструктора |
| `scraped_at` | Авто | `datetime.now()` |

### 5.4. Checkpoint

После scraping каждой компании — сохранять промежуточный результат в SQLite через `_save_checkpoint()`. Это позволяет:
- Не потерять данные при падении скрепера на середине.
- Запустить скрепер повторно без дублирования (raw_companies допускает дубли — dedup разберётся).

---

## 6. Оценка трудозатрат по источникам

| Источник | Добавление | Поддержка | Уникальность | Рекомендация |
|---|---|---|---|---|
| JSprav | ✅ Уже в плане | Низкая | Высокая | Основной источник |
| 2GIS | ✅ Уже в плане | Средняя (селекторы) | Высокая | Обязателен |
| Yell | ✅ Уже в плане | Средняя | Средняя | Полезен |
| Firmsru | ✅ Уже в плане | Низкая | Низкая | Дополнение |
| Firecrawl | ✅ Уже в плане | Низкая | Высокая (уникальные сайты) | Полезен |
| Google Maps | ⏳ В плане (off) | Высокая | Высокая | Будущее |
| Яндекс.Карты | 🔲 Не в плане | Высокая | Очень высокая | **Второй приоритет после Google Maps** |
| Zoon.ru | 🔲 Не в плане | Низкая | Средняя | **Рекомендую добавить** |
| Spravker.ru | 🔲 Не в плане | Низкая | Средняя (малые города) | Попробовать |
| VK поиск | 🔲 Не в плане | Очень высокая | Высокая | Только через API, не через Playwright |
| Google поиск | 🔄 Уже в tg_finder | Средняя | Средняя | Дублирует Firecrawl |
| Avito | ⏳ В плане (off) | Высокая | Низкая | Много мусора, сомнительная ценность |
| Юла | 🔲 Не в плане | Средняя | Очень низкая | Объединена с Авито, не стоит |
| Ritual.ru | 🔲 Не в плане | Средняя | Низкая | Национальный, без городской привязки |
