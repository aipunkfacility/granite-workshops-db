#!/usr/bin/env python3
"""
Скрипт для поиска ссылок на VK, WhatsApp и Telegram на сайтах компаний
Согласно инструкциям из prompt_messengers_deep_search.md
"""

import csv
import re
import time
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

# Конфигурация
INPUT_CSV = "rostov_enriched.csv"
OUTPUT_CSV = "rostov_enriched_2.csv"
REQUEST_TIMEOUT = 10
DELAY_BETWEEN_REQUESTS = 1  # секунда между запросами к одному домену

# Компании без сайта (не трогать)
NO_SITE_COMPANIES = {
    "CMP0023",
    "CMP0031",
    "CMP0062",
    "CMP0065",
    "CMP0084",
    "CMP0094",
    "CMP0097",
    "CMP0098",
    "CMP0107",
    "CMP0108",
}

# Паттерны для поиска ссылок
VK_PATTERNS = [r'vk\.com/[^\s"\'>]+', r'https?://vk\.com/[^\s"\'>]+']

TELEGRAM_PATTERNS = [r't\.me/[^\s"\'>]+', r'https?://t\.me/[^\s"\'>]+']

WHATSAPP_PATTERNS = [
    r'wa\.me/[^\s"\'>]+',
    r'https?://wa\.me/[^\s"\'>]+',
    r'api\.whatsapp\.com/send\?phone=[^\s"\'>]+',
]


def normalize_phone(phone):
    """Нормализация телефонного номера к формату 7XXXXXXXXXXX"""
    if not phone:
        return None

    # Удаляем все кроме цифр
    digits = re.sub(r"\D", "", phone)

    # Если начинается с 8, заменяем на 7
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]

    # Проверяем, что начинается с 7 и имеет 11 цифр
    if digits.startswith("7") and len(digits) == 11:
        return digits

    return None


def extract_links_from_text(text, patterns):
    """Извлечение ссылок по паттернам из текста"""
    links = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        links.extend(matches)
    return links


def normalize_vk_link(link):
    """Нормализация ссылки VK к полному формату"""
    link = link.strip()
    if not link.startswith("http"):
        if link.startswith("vk.com/"):
            link = "https://" + link
        else:
            link = "https://vk.com/" + link
    return link


def normalize_telegram_link(link):
    """Нормализация ссылки Telegram к полному формату"""
    link = link.strip()
    # Убираем @ если есть
    if link.startswith("@"):
        link = link[1:]

    if not link.startswith("http"):
        if link.startswith("t.me/"):
            link = "https://" + link
        else:
            link = "https://t.me/" + link
    return link


def normalize_whatsapp_link(phone):
    """Нормализация телефона к ссылке WhatsApp"""
    normalized = normalize_phone(phone)
    if normalized:
        return f"https://wa.me/{normalized}"
    return None


def fetch_page(url):
    """Получение веб-страницы с обработкой ошибок"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Ошибка при загрузке {url}: {str(e)}")
        return None


def extract_links_from_page(html, base_url):
    """Извлечение всех ссылок со страницы"""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    links = []

    # Находим все ссылки с href
    for tag in soup.find_all(["a", "link"], href=True):
        href = tag["href"].strip()
        if href:
            # Делаем абсолютной ссылку, если нужно
            absolute_url = urljoin(base_url, href)
            links.append(absolute_url)

    # Также ищем в тексте страницы
    text_content = soup.get_text()
    links.extend(extract_links_from_text(text_content, VK_PATTERNS))
    links.extend(extract_links_from_text(text_content, TELEGRAM_PATTERNS))
    links.extend(extract_links_from_text(text_content, WHATSAPP_PATTERNS))

    return links


def search_messengers_on_site(company_name, city, website):
    """Поиск мессенджеров на сайте компании"""
    if not website or website.strip() == "":
        return None, None, None

    print(f"Обрабатываем {company_name} ({city}) - {website}")

    # Нормализуем URL
    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    vk_link = None
    telegram_link = None
    whatsapp_link = None

    # Список страниц для проверки
    pages_to_check = [
        website,  # Главная
        urljoin(website, "/contacts"),
        urljoin(website, "/kontakty"),
        urljoin(website, "/#contact"),
        urljoin(website, "/about"),
        urljoin(website, "/o-nas"),
        urljoin(website, "/company"),
    ]

    # Убираем дубликаты
    pages_to_check = list(dict.fromkeys(pages_to_check))

    all_found_links = []

    for page_url in pages_to_check:
        print(f"  Проверяем {page_url}")
        html = fetch_page(page_url)
        if html:
            links = extract_links_from_page(html, page_url)
            all_found_links.extend(links)
            time.sleep(DELAY_BETWEEN_REQUESTS)

    # Также проверяем текст всей страницы на наличие ссылок
    # (уже сделано в extract_links_from_page)

    # Обрабатываем найденные ссылки
    for link in all_found_links:
        link_lower = link.lower()

        # Проверяем VK
        if not vk_link and any(
            pattern in link_lower for pattern in ["vk.com/", "vkontakte.ru/"]
        ):
            vk_link = normalize_vk_link(link)

        # Проверяем Telegram
        if not telegram_link and any(
            pattern in link_lower for pattern in ["t.me/", "telegram.me/"]
        ):
            telegram_link = normalize_telegram_link(link)

        # Проверяем WhatsApp в ссылках
        if not whatsapp_link and any(
            pattern in link_lower for pattern in ["wa.me/", "whatsapp.com/"]
        ):
            # Извлекаем номер из ссылки WhatsApp
            phone_match = re.search(r"(\d{11,})", link)
            if phone_match:
                phone = phone_match.group(1)
                # Если начинается с 8, заменяем на 7
                if phone.startswith("8") and len(phone) == 11:
                    phone = "7" + phone[1:]
                whatsapp_link = normalize_whatsapp_link(phone)

    # Если не нашли через ссылки, ищем в тексте номера телефонов с пометкой WhatsApp
    if not whatsapp_link:
        # Здесь можно добавить поиск по тексту с регулярными выражениями для телефонов
        pass

    return vk_link, telegram_link, whatsapp_link


def main():
    """Основная функция"""
    print("Начинаем обработку компаний...")

    # Читаем исходный CSV
    companies = []
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            companies.append(row)

    # Обрабатываем каждую компанию
    updated_companies = []
    stats = {
        "total": len(companies),
        "no_site": 0,
        "already_complete": 0,
        "processed": 0,
        "errors": 0,
    }

    for company in companies:
        company_id = company["ID"]

        # Пропускаем компании без сайта
        if company_id in NO_SITE_COMPANIES:
            stats["no_site"] += 1
            updated_companies.append(company)
            continue

        # Проверяем, уже ли заполнены все мессенджеры
        vk = company["VK"].strip()
        telegram = company["Telegram"].strip()
        whatsapp = company["WhatsApp"].strip()

        if vk and telegram and whatsapp:
            stats["already_complete"] += 1
            updated_companies.append(company)
            continue

        # Обрабатываем компанию
        try:
            website = company["Сайт"].strip()
            new_vk, new_telegram, new_whatsapp = search_messengers_on_site(
                company["Название"], company["Город"], website
            )

            # Обновляем только пустые поля, не перезаписываем уже заполненные
            if not vk and new_vk:
                company["VK"] = new_vk
            if not telegram and new_telegram:
                company["Telegram"] = new_telegram
            if not whatsapp and new_whatsapp:
                company["WhatsApp"] = new_whatsapp

            stats["processed"] += 1
            updated_companies.append(company)

        except Exception as e:
            print(f"Ошибка при обработке компании {company_id}: {str(e)}")
            stats["errors"] += 1
            updated_companies.append(company)  # Добавляем без изменений

    # Записываем результат
    fieldnames = [
        "ID",
        "Название",
        "Город",
        "Телефон",
        "Email",
        "Сайт",
        "Адрес",
        "VK",
        "Telegram",
        "WhatsApp",
        "Статус",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_companies)

    # Выводим статистику
    print("\n=== Обработка завершена ===")
    print(f"Всего компаний: {stats['total']}")
    print(f"Без сайта: {stats['no_site']}")
    print(f"Уже заполнено все: {stats['already_complete']}")
    print(f"Обработано: {stats['processed']}")
    print(f"Ошибок: {stats['errors']}")
    print(f"Результат сохранен в {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
