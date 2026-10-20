#!/usr/bin/env python3
"""Parser and writer for .sd.xml sprite-definition files."""

import os
import shutil
import xml.etree.ElementTree as ET


def _int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


class Page:
    def __init__(self, file_name, width, height):
        self.file_name, self.width, self.height = file_name, width, height


class Sprite:
    def __init__(self, element, owner, page_index):
        self.element = element
        self.owner = owner
        self.page_index = page_index
        self.name = element.get("name", "")
        self.x = _int(element.get("x"))
        self.y = _int(element.get("y"))
        self.w = _int(element.get("w"))
        self.h = _int(element.get("h"))
        self._orig = self.crop

    @property
    def crop(self):
        return (self.x, self.y, self.w, self.h)

    @crop.setter
    def crop(self, v):
        self.x, self.y, self.w, self.h = v

    @property
    def dirty(self):
        return self.crop != self._orig

    @property
    def page_file(self):
        return self.owner.pages[self.page_index].file_name

    def commit(self):
        for k, v in zip("xywh", self.crop):
            self.element.set(k, str(v))
        self._orig = self.crop


class SdFile:
    def __init__(self, path):
        self.path = path
        self.tree = ET.parse(path)
        self.root = self.tree.getroot()
        self.pages, self.sprites = [], []
        for i, page in enumerate(self.root.findall("page")):
            self.pages.append(Page(page.get("file", "Unknown"), _int(page.get("w")), _int(page.get("h"))))
            for el in page.findall("sprite"):
                self.sprites.append(Sprite(el, self, i))

    @property
    def basename(self):
        return os.path.basename(self.path)

    @property
    def dirty(self):
        return any(s.dirty for s in self.sprites)

    def save(self):
        """Write changes. The first save keeps the untouched original as .bak."""
        backup = self.path + ".bak"
        if not os.path.exists(backup):
            shutil.copy2(self.path, backup)
        for s in self.sprites:
            s.commit()
        self.tree.write(self.path, encoding="utf-8", xml_declaration=True)


def locate_xml(game_root, culture, name):
    c = culture.lower()
    for p in (
        os.path.join(game_root, "data", "ui", "roman", "interface", name),
        os.path.join(game_root, "data", "ui", c, "interface", name),
        os.path.join(game_root, "data", "ui", "roman", name),
        os.path.join(game_root, "data", "ui", c, name),
        os.path.join(game_root, "data", "ui", name),
    ):
        if os.path.exists(p):
            return p
    return None
