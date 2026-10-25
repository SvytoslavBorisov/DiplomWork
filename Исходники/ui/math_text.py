"""Сохраняет совместимость смешанного текста с единым математическим рендерером."""

from functools import lru_cache
import html
import re

from .math_renderer import inline_formula


_SYMBOL = re.compile(r"\$([^$]+)\$|O\((?:[^()]|\([^()]*\))*\)|Σₛ|Σ_s|2\^(?:\{[^}]+\}|[a-zA-Z0-9]+)|(?<![\w])[hgnkNdsQLSXEψΣ](?![\w])")


@lru_cache(maxsize=1024)
def math_html(text: str) -> str:
    if not _SYMBOL.search(text):
        return text
    parts = []
    start = 0
    for match in _SYMBOL.finditer(text):
        parts.append(html.escape(text[start:match.start()]))
        symbol = match.group(1) or match.group()
        symbol = {"Σₛ": r"\Sigma_s", "Σ_s": r"\Sigma_s", "Σ": r"\Sigma", "ψ": r"\psi"}.get(symbol, symbol)
        parts.append(inline_formula(symbol))
        start = match.end()
    parts.append(html.escape(text[start:]))
    return '<span>' + ''.join(parts) + '</span>'
