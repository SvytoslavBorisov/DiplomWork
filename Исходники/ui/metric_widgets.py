"""Форматирует счётчики для интерфейса без устаревших карточек сравнения."""

def formatted_number(value: int | None) -> str:
    return "–" if value is None else f"{value:,}".replace(",", " ")
