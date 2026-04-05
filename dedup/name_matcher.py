# dedup/name_matcher.py
from utils import compare_names


def find_name_matches(companies: list[dict], threshold: int = 88) -> list[list[int]]:
    """Поиск дубликатов по названиям через fuzzy matching.

    Args:
        companies: список dict с полями {"id": int, "name": str, "address": str}
        threshold: порог схожести (0-100, из config.yaml dedup.name_similarity_threshold)

    Returns:
        Список пар/групп: [[id1, id2], ...] — похожие названия
    """
    matches = []
    n = len(companies)

    for i in range(n):
        for j in range(i + 1, n):
            if compare_names(companies[i]["name"], companies[j]["name"], threshold):
                matches.append([companies[i]["id"], companies[j]["id"]])

    return matches
