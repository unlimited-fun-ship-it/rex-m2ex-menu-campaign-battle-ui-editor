#!/usr/bin/env python3
"""
Procedural parser for .sd.xml files.
"""

import xml.etree.ElementTree as ET

def parse_sd_xml(filepath):
    """Parses the XML and returns a dictionary of pages, a list of sprites, and the root element."""
    pages = []
    sprites = []
    tree = ET.parse(filepath)
    root = tree.getroot()

    for page_index, page_elem in enumerate(root.findall("page")):
        file_name = page_elem.get("file", "Unknown")
        width = int(page_elem.get("w", 0))
        height = int(page_elem.get("h", 0))
        
        pages.append({
            "file_name": file_name,
            "width": width,
            "height": height
        })

        for sprite_elem in page_elem.findall("sprite"):
            sprites.append({
                "name": sprite_elem.get("name", ""),
                "x": int(sprite_elem.get("x", 0)),
                "y": int(sprite_elem.get("y", 0)),
                "w": int(sprite_elem.get("w", 0)),
                "h": int(sprite_elem.get("h", 0)),
                "alpha": int(sprite_elem.get("alpha", 1)),
                "cursor": int(sprite_elem.get("cursor", 0)),
                "element_ref": sprite_elem,
                "page_index": page_index
            })

    return {"pages": pages, "sprites": sprites, "root": root, "filepath": filepath}

def save_sd_xml(xml_data):
    """Writes the modified sprite data back to the XML file."""
    if xml_data["root"] is None:
        return

    for spr in xml_data["sprites"]:
        if spr["element_ref"] is not None:
            spr["element_ref"].set("x", str(spr["x"]))
            spr["element_ref"].set("y", str(spr["y"]))
            spr["element_ref"].set("w", str(spr["w"]))
            spr["element_ref"].set("h", str(spr["h"]))

    tree = ET.ElementTree(xml_data["root"])
    tree.write(xml_data["filepath"], encoding="utf-8", xml_declaration=True)