#!/usr/bin/env python3
"""
Parser for the .sd.xml format used by REX and modern Total War modding.
Adapted for the <page file="..." w="..." h="..."> structure.
"""

import xml.etree.ElementTree as ET

class SpritePage:
    def __init__(self, file_name, width, height):
        self.file_name = file_name
        self.width = width
        self.height = height

class SpriteElement:
    def __init__(self, name, x, y, w, h, alpha=1, cursor=0):
        self.name = name
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.alpha = alpha
        self.cursor = cursor
        self.element_ref = None # Reference to the XML element for saving

class SDXMLReader:
    def __init__(self, filepath):
        self.filepath = filepath
        self.pages = []          # list of SpritePage
        self.sprites = []        # list of SpriteElement
        self.root = None
        self._parse()

    def _parse(self):
        tree = ET.parse(self.filepath)
        self.root = tree.getroot()

        # Parse pages
        for page_elem in self.root.findall("page"):
            file_name = page_elem.get("file", "Unknown")
            width = int(page_elem.get("w", 0))
            height = int(page_elem.get("h", 0))
            self.pages.append(SpritePage(file_name, width, height))

            # Parse sprites within this page
            for sprite_elem in page_elem.findall("sprite"):
                sprite = SpriteElement(
                    name=sprite_elem.get("name", ""),
                    x=int(sprite_elem.get("x", 0)),
                    y=int(sprite_elem.get("y", 0)),
                    w=int(sprite_elem.get("w", 0)),
                    h=int(sprite_elem.get("h", 0)),
                    alpha=int(sprite_elem.get("alpha", 1)),
                    cursor=int(sprite_elem.get("cursor", 0))
                )
                sprite.element_ref = sprite_elem
                sprite.page_index = len(self.pages) - 1 # Store which page it belongs to
                self.sprites.append(sprite)

    def save(self):
        """Write the modified sprite data back to the XML file."""
        if self.root is None:
            return

        # Update the XML tree with any changes made to the sprite objects
        for spr in self.sprites:
            if spr.element_ref is not None:
                spr.element_ref.set("x", str(spr.x))
                spr.element_ref.set("y", str(spr.y))
                spr.element_ref.set("w", str(spr.w))
                spr.element_ref.set("h", str(spr.h))

        tree = ET.ElementTree(self.root)
        tree.write(self.filepath, encoding="utf-8", xml_declaration=True)