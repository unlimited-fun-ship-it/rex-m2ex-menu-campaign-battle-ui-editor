#!/usr/bin/env python3
"""
Functional asset handling using memoization.
"""

import os
from functools import lru_cache
from PIL import Image
from PyQt5.QtGui import QIcon, QPixmap, QImage

@lru_cache(maxsize=None)
def load_image_cached(filepath: str):
    """Memoized image loading (pure from the caller's perspective)."""
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        return Image.open(filepath).convert("RGBA")
    except Exception:
        return None

def get_image_path(game_root: str, culture: str, filename: str) -> str:
    if not game_root:
        return None

    if "radar_map" in filename.lower():
        primary_dir = os.path.join(game_root, "data", "world", "maps", "campaign", "imperial_campaign")
        if os.path.isdir(primary_dir):
            for candidate in ["radar_map2.tga", "radar_map1.tga"]:
                if os.path.exists(os.path.join(primary_dir, candidate)):
                    return os.path.join(primary_dir, candidate)

    search_dirs = (
        os.path.join(game_root, "data", "ui", "roman", "interface"),
        os.path.join(game_root, "data", "ui", culture, "interface"),
        os.path.join(game_root, "data", "ui", "roman"),
        os.path.join(game_root, "data", "ui", culture),
        os.path.join(game_root, "data", "ui")
    )
    
    for d in search_dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.lower() == filename.lower():
                    return os.path.join(d, f)
    return None

def get_thumbnail(tga_path: str, x: int, y: int, w: int, h: int) -> QIcon:
    full_img = load_image_cached(tga_path)
    if not full_img:
        return QIcon()

    try:
        crop = full_img.crop((x, y, x + w, y + h))
        crop.thumbnail((48, 48), Image.Resampling.LANCZOS)
        data = crop.tobytes("raw", "RGBA")
        qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
        return QIcon(QPixmap.fromImage(qim))
    except Exception:
        return QIcon()