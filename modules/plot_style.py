from __future__ import annotations

from functools import lru_cache

import matplotlib
from matplotlib import font_manager, ft2font


FONT_CANDIDATES = [
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Noto Sans CJK TC",
    "Noto Sans SC",
    "Microsoft YaHei",
    "SimHei",
    "Arial Unicode MS",
    "DejaVu Sans",
]


@lru_cache(maxsize=1)
def choose_plot_font() -> str:
    available_fonts = {font.name: font.fname for font in font_manager.fontManager.ttflist}
    for font_name in FONT_CANDIDATES:
        font_path = available_fonts.get(font_name)
        if font_path and supports_required_glyphs(font_path):
            return font_name
    return "DejaVu Sans"


def supports_required_glyphs(font_path: str) -> bool:
    if "DejaVuSans" in font_path or "DejaVu Sans" in font_path:
        return True
    try:
        charmap = ft2font.FT2Font(font_path).get_charmap()
    except Exception:
        return False
    probe_chars = "靶点疾病图"
    return all(ord(char) in charmap for char in probe_chars)


def configure_matplotlib_fonts(base_size: int | None = None) -> str:
    font_name = choose_plot_font()
    rc_updates = {
        "font.family": "sans-serif",
        "font.sans-serif": [font_name, *FONT_CANDIDATES],
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
    }
    if base_size is not None:
        rc_updates["font.size"] = base_size
    matplotlib.rcParams.update(rc_updates)
    return font_name
