#!/usr/bin/env python3
"""
Handles finding files (case-insensitive), loading images, and generating thumbnails.
"""

import os
import logging
from PIL import Image
from PyQt5.QtGui import QIcon, QPixmap, QImage

class AssetManager:
    def __init__(self):
        self.image_cache = {}

    def clear_cache(self):
        self.image_cache.clear()

    def get_image_path(self, game_root, culture, filename):
        """Finds the image path, handling case-sensitivity and minimap exceptions."""
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

    def get_thumbnail(self, tga_path, x, y, w, h):
        if not tga_path or not os.path.exists(tga_path):
            return QIcon()
            
        if tga_path not in self.image_cache:
            try:
                self.image_cache[tga_path] = Image.open(tga_path).convert("RGBA")
            except Exception:
                return QIcon()

        try:
            full_img = self.image_cache[tga_path]
            crop = full_img.crop((x, y, x + w, y + h))
            crop.thumbnail((48, 48), Image.Resampling.LANCZOS)
            data = crop.tobytes("raw", "RGBA")
            qim = QImage(data, crop.width, crop.height, QImage.Format_RGBA8888)
            pix = QPixmap.fromImage(qim)
            return QIcon(pix)
        except Exception:
            return QIcon()

    def load_image(self, filepath):
        """Loads an image for rendering on the canvas."""
        if filepath not in self.image_cache:
            try:
                self.image_cache[filepath] = Image.open(filepath).convert("RGBA")
            except Exception as e:
                logging.error(f"Failed to load image {filepath}: {e}")
                return None
        return self.image_cache[filepath]