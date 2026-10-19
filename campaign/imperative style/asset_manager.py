#!/usr/bin/env python3
"""
Procedural asset handling with a global cache.
"""

import os
import logging
from PIL import Image
from PyQt5.QtGui import QIcon, QPixmap, QImage

IMAGE_CACHE = {}

def clear_cache():
    global IMAGE_CACHE
    IMAGE_CACHE.clear()

def get_image_path(game_root, culture, filename):
    if not game_root:
        return None

    if "radar_map" in filename.lower():
        primary_dir = os.path.join(game_root, "data", "world", "maps", "campaign", "imperial_campaign")
        if os.path.isdir(primary_dir):
            for candidate in ["radar_map2.tga", "radar_map1.tga"]:
                for f in os.listdir(primary_dir):
                    if f.lower() == candidate:
                        return os.path.join(primary_dir, f)

    search_dirs = [
        os.path.join(game_root, "data", "ui", "roman", "interface"),
        os.path.join(game_root, "data", "ui", culture, "interface"),
        os.path.join(game_root, "data", "ui", "roman"),
        os.path.join(game_root, "data", "ui", culture),
        os.path.join(game_root, "data", "ui")
    ]
    
    for d in search_dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.lower() == filename.lower():
                    return os.path.join(d, f)
    return None

def get_thumbnail(tga_path, x, y, w, h):
    if not tga_path or not os.path.exists(tga_path):
        return QIcon()
        
    if tga_path not in IMAGE_CACHE:
        try:
            IMAGE_CACHE[tga_path] = Image.open(tga_path).convert("RGBA")
        except Exception:
            return QIcon()

    try:
        full_img = IMAGE_CACHE[tga_path]
        crop = full_img.crop((x, y, x + w, y + h))
        crop.thumbnail((48, 48), Image.Resampling.LANCZOS)
        data = crop.tobytes("raw", "RGBA")
        qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
        pix = QPixmap.fromImage(qim)
        return QIcon(pix)
    except Exception:
        return QIcon()

def load_image(filepath):
    if filepath not in IMAGE_CACHE:
        try:
            IMAGE_CACHE[filepath] = Image.open(filepath).convert("RGBA")
        except Exception as e:
            logging.error(f"Failed to load image {filepath}: {e}")
            return None
    return IMAGE_CACHE[filepath]