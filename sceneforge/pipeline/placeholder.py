from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageStat

COLOR_TOKEN = "__COLOR__"


def placeholder_module(image: bytes, template: Path) -> str:
    return template.read_text(encoding="utf-8").replace(COLOR_TOKEN, f"0x{median_color(image)}")


def median_color(image: bytes) -> str:
    with Image.open(io.BytesIO(image)) as picture:
        rgb = picture.convert("RGB")
    width, height = rgb.size
    center = rgb.crop((width // 4, height // 4, width - width // 4, height - height // 4))
    red, green, blue = ImageStat.Stat(center).median
    return f"{red:02x}{green:02x}{blue:02x}"
