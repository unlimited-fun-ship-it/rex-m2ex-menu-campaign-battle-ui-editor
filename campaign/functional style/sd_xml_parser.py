#!/usr/bin/env python3
"""
Pure functional parser for .sd.xml files using frozen dataclasses.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Tuple, Optional

@dataclass(frozen=True)
class SpritePage:
    file_name: str
    width: int
    height: int

@dataclass(frozen=True)
class SpriteElement:
    name: str
    x: int
    y: int
    w: int
    h: int
    page_index: int
    element_ref: Optional[ET.Element] # Kept for saving

def parse_sd_xml(filepath: str) -> Tuple[Tuple[SpritePage, ...], Tuple[SpriteElement, ...], ET.Element, str]:
    """Returns immutable tuples of pages and sprites."""
    tree = ET.parse(filepath)
    root = tree.getroot()

    pages = []
    sprites = []

    for page_index, page_elem in enumerate(root.findall("page")):
        page = SpritePage(
            file_name=page_elem.get("file", "Unknown"),
            width=int(page_elem.get("w", 0)),
            height=int(page_elem.get("h", 0))
        )
        pages.append(page)

        for sprite_elem in page_elem.findall("sprite"):
            sprite = SpriteElement(
                name=sprite_elem.get("name", ""),
                x=int(sprite_elem.get("x", 0)),
                y=int(sprite_elem.get("y", 0)),
                w=int(sprite_elem.get("w", 0)),
                h=int(sprite_elem.get("h", 0)),
                page_index=page_index,
                element_ref=sprite_elem
            )
            sprites.append(sprite)

    return tuple(pages), tuple(sprites), root, filepath

def save_sd_xml(root: ET.Element, sprites: Tuple[SpriteElement, ...], filepath: str) -> None:
    """Imperative boundary: writes to file."""
    if root is None:
        return

    for spr in sprites:
        if spr.element_ref is not None:
            spr.element_ref.set("x", str(spr.x))
            spr.element_ref.set("y", str(spr.y))
            spr.element_ref.set("w", str(spr.w))
            spr.element_ref.set("h", str(spr.h))

    tree = ET.ElementTree(root)
    tree.write(filepath, encoding="utf-8", xml_declaration=True)