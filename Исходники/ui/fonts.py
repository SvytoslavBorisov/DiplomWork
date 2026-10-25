"""Загружает локальный шрифт интерфейса из ресурсов приложения."""

from functools import lru_cache
from pathlib import Path
import os
import sys

from PySide6.QtGui import QFont, QFontDatabase


def configure_platform_rendering() -> None:
    """Выбирает сглаженный FreeType для локального TTF до создания QApplication."""
    if sys.platform == "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows:fontengine=freetype")


@lru_cache(maxsize=1)
def header_font_family() -> str:
    path = Path(__file__).with_name("resources") / "fonts" / "FredokaOneCyrillic-Regular.ttf"
    font_id = QFontDatabase.addApplicationFont(str(path))
    families = QFontDatabase.applicationFontFamilies(font_id)
    if font_id < 0 or not families:
        raise RuntimeError(f"Не удалось загрузить шрифт интерфейса: {path}")
    return families[0]


@lru_cache(maxsize=1)
def math_font_family() -> str:
    """Загружает математические символы STIX из установленного Matplotlib."""
    from matplotlib import get_data_path
    path=Path(get_data_path()) / "fonts" / "ttf" / "STIXGeneralBol.ttf"
    font_id=QFontDatabase.addApplicationFont(str(path))
    families=QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        raise RuntimeError("Не удалось загрузить математический шрифт STIX.")
    return families[0]


def configure_application_fonts(app) -> None:
    """Применяет Fredoka к обычному тексту Qt и Matplotlib."""
    family = header_font_family()
    math_font_family()
    font = QFont(family)
    font.setPixelSize(13)
    app.setFont(font)
    from matplotlib import font_manager, rcParams
    path = Path(__file__).with_name("resources") / "fonts" / "FredokaOneCyrillic-Regular.ttf"
    if not any(item.fname == str(path) for item in font_manager.fontManager.ttflist):
        font_manager.fontManager.addfont(str(path))
    rcParams.update({"font.family": family, "font.weight": "normal", "mathtext.fontset": "stix"})
