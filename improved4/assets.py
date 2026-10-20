#!/usr/bin/env python3
"""Image lookup, loading and caching (case-insensitive file search)."""

import os
import logging
from PIL import Image
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap, QImage

log = logging.getLogger(__name__)
LANCZOS = getattr(Image, "Resampling", Image).LANCZOS


def pil_to_pixmap(img):
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    # .copy() detaches the QImage from the Python bytes buffer
    qim = QImage(data, img.width, img.height, img.width * 4, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(qim)


class AssetManager:
    def __init__(self):
        self.game_root = ""
        self.culture = "roman"
        self._images = {}
        self._crops = {}
        self._dirs = {}

    def configure(self, game_root, culture):
        self.game_root = game_root
        self.culture = culture.lower()
        self._images.clear()
        self._crops.clear()
        self._dirs.clear()

    # ---- file lookup -------------------------------------------------
    def _listing(self, directory):
        """lowercase-name -> real-name map for a directory (cached)."""
        if directory not in self._dirs:
            try:
                self._dirs[directory] = {f.lower(): f for f in os.listdir(directory)}
            except OSError:
                self._dirs[directory] = {}
        return self._dirs[directory]

    def search_dirs(self):
        r, c = self.game_root, self.culture
        return [
            os.path.join(r, "data", "ui", "roman", "interface"),
            os.path.join(r, "data", "ui", c, "interface"),
            os.path.join(r, "data", "ui", "roman"),
            os.path.join(r, "data", "ui", c),
            os.path.join(r, "data", "ui"),
        ]

    def find(self, filename):
        if not self.game_root or not filename:
            return None
        if "radar_map" in filename.lower():
            d = os.path.join(self.game_root, "data", "world", "maps", "campaign", "imperial_campaign")
            listing = self._listing(d)
            for cand in ("radar_map2.tga", "radar_map1.tga"):
                if cand in listing:
                    return os.path.join(d, listing[cand])
        for d in self.search_dirs():
            real = self._listing(d).get(filename.lower())
            if real:
                return os.path.join(d, real)
        return None

    # ---- loading -----------------------------------------------------
    def image(self, path):
        if path not in self._images:
            try:
                self._images[path] = Image.open(path).convert("RGBA")
            except Exception as e:
                log.error("Failed to load image %s: %s", path, e)
                self._images[path] = None
        return self._images[path]

    def crop_pixmap(self, filename, x, y, w, h):
        if w <= 0 or h <= 0:
            return None
        path = self.find(filename)
        if not path:
            return None
        key = (path, x, y, w, h)
        if key not in self._crops:
            img = self.image(path)
            self._crops[key] = pil_to_pixmap(img.crop((x, y, x + w, y + h))) if img else None
        return self._crops[key]

    def sprite_pixmap(self, sprite):
        return self.crop_pixmap(sprite.page_file, sprite.x, sprite.y, sprite.w, sprite.h)

    def sprite_icon(self, sprite, size=48):
        pm = self.sprite_pixmap(sprite)
        if pm is None:
            return QIcon()
        return QIcon(pm.scaled(QSize(size, size), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def minimap_pixmap(self, size):
        path = self.find("radar_map2.tga")
        img = self.image(path) if path else None
        if img is None:
            return None
        return pil_to_pixmap(img.resize(size, LANCZOS))
