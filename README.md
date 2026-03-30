# Funeral Agency Database

## Обзор

Сбор базы ритуальных агентств и производителей памятников по городам России. Используется для поиска подрядчиков (ретушеров) и рассылки предложений.

## Workflow (3 этапа)

### Этап 1: Сбор базы → `companies.md`

Собрать ВСЕ организации из источников:
- **Карты:** 2GIS, Яндекс.Карты, Google Maps
- **Каталоги:** Yell, JSprav, Firmsru
- **Доски объявлений:** Авито, Юла

**Цель — сотни компаний!** Без фильтрации.

### Этап 2: Обогащение Telegram

Для каждого номера телефона:
```
"{номер}" Telegram
```

Добавить username в профиль компании.

### Этап 3: Приоритизация

- **С Telegram** → `data.md`, `summary.md`, `report.md` (приоритет для работы)
- **Без Telegram** → остаются в `companies.md` (в работе)

## Структура данных

```
funeral-agency-db/
├── config.yaml              # 44 города России
├── sources/
│   └── directories.md       # Источники для поиска
├── agents/
│   └── funeral-scraper.md  # Агент сбора
├── scripts/
│   ├── scrape_city.py      # Python скрипт сбора
│   └── pyproject.toml     # Зависимости
├── cities/
│   └── {city-name}/
│       ├── companies.md     # ВСЕ компании (база)
│       ├── companies.json   # JSON с данными
│       ├── data.md         # Только с Telegram (приоритет)
│       ├── summary.md      # Саммари с Telegram
│       └── report.md       # Отчёт с рекомендациями
└── reports/
    └── progress.md         # Прогресс обработки
```

## Приоритет контактов

**Telegram > WhatsApp > Email > Телефон**

Для каждой компании записывать полные ссылки:
- Telegram: `https://t.me/username`
- WhatsApp: `https://wa.me/79xxxxxxxxx`

## Что собирать

### Обязательно
- Название организации
- Телефон (формат +7XXX...)
- Адрес
- Сайт
- Email (искать на сайте!)

### Соцсети и мессенджеры
- **Telegram** — полная ссылка t.me/username
- **WhatsApp** — полная ссылка wa.me/79xxxxxxxxx
- **VK** — группа
- **OK** — группа

### Дополнительно
- Упоминание ретуши/обработки фото
- Собственное производство
- Станки (лазерные, ударные)

## Поиск Telegram по номеру (ОБЯЗАТЕЛЬНО!)

Для каждого номера:
```
"{номер}" Telegram
```

Примеры:
- `+7 903 955 81 17 Telegram` → t.me/evlitos
- `8 937 821 77 77 Telegram` → t.me/username (если найден)

## Формат файлов

### companies.md

```markdown
# Компании — Астрахань

**Дата сбора:** 2026-03-14
**Источники:** 2GIS, JSprav, Yell
**Всего:** 50 компаний

---

## 1. Название компании

**Телефон:** +7XXX...
**Адрес:** г. Город, ул. Улица, 1
**Сайт:** https://site.ru
**Email:** email@domain.ru

**Telegram:** t.me/username (если найден)
**WhatsApp:** wa.me/79xxxxxxxxx

**Особенности:**
- Собственное производство
- Делают ретушь
```

### data.md (только с Telegram)

```markdown
# Компании с Telegram — Астрахань

**Всего с Telegram:** 10 компаний

---

## 1. Название

**Telegram:** https://t.me/username
**WhatsApp:** https://wa.me/79xxxxxxxxx
...
```

## Скрипты

### scrape_city.py

```bash
cd scripts/
python -m uv venv
python -m uv pip install -r pyproject.toml
python scrape_city.py astrakhan
```

### Зависимости
- requests
- beautifulsoup4
- lxml
- playwright (для динамических страниц)

## Процесс работы

1. Назвать город для обработки
2. Этап 1: Сбор всех компаний → `companies.md`
3. Этап 2: Поиск Telegram для каждого номера
4. Этап 3: Приоритизация (с TG → data.md, без → companies.md)
5. Показать результат
6. Ждать подтверждения для следующего города

## Важно

- **Собрать сотни компаний** — чем больше, тем лучше
- **Для каждого номера искать Telegram** — ключевая задача
- **Полные ссылки t.me** — записывать username
- **Не придумывать данные** — только факты из источников
- **Объединение (merge)** — дубликаты соединяются, не удаляются
