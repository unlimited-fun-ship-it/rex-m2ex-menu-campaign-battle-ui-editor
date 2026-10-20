#!/usr/bin/env python3
"""Configuration, constants and logging setup (no side effects on import)."""

import os
import glob
import logging
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# One output folder per launch. It is NOT created at startup: it appears the
# first time something needs it (error log written, screenshot/export, layout save).
NOW_STR = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, f"output_{NOW_STR}")
LAYOUT_FILENAME = "hud_layout.json"
LOG_FILENAME = "editor_log.txt"
LEGACY_LAYOUT_FILE = os.path.join(SCRIPT_DIR, LAYOUT_FILENAME)  # older versions saved here

CANVAS_W, CANVAS_H = 1024, 768
CULTURES = ["Roman", "Greek", "Eastern", "Barbarian", "Carthaginian", "Egyptian"]
REQUIRED_XMLS = ["strat3.sd.xml", "shared2.sd.xml", "radar.sd.xml"]

DEFAULT_LAYOUT = {
    "STRAT_HUD_LEFT": (0, 587),
    "STRAT_HUD_MIDDLE": (281, 621),
    "STRAT_HUD_RIGHT": (743, 587),
    "TAB_ARMY_ASSEMBLY": (347, 596),
    "TAB_TOWN_ASSEMBLY": (430, 596),
    "TAB_AGENTS_ASSEMBLY": (509, 596),
    "TAB_EXTRA_ASSEMBLY": (594, 596),
    "RADAR_BUTTON_PLUS": (3, 745),
    "RADAR_BUTTON_MINUS": (27, 745),
    "BUILD_BUTTON_IMAGE": (760, 620),
    "TRAIN_BUTTON_IMAGE": (760, 695),
    "BUTTON_OUTER_RING_LRG": (880, 650),
    "FACTION_LOGO_ALEMANNI": (897, 667),
    "END_TURN_BUTTON_IMAGE": (970, 680),
    "SEASON_ICON_SUMMER": (955, 635),
}

BACKGROUNDS = ["STRAT_HUD_LEFT", "STRAT_HUD_MIDDLE", "STRAT_HUD_RIGHT"]

DRAW_ORDER = [
    "BUTTON_OUTER_RING_LRG", "FACTION_LOGO_ALEMANNI",
    "RADAR_BUTTON_MINUS", "RADAR_BUTTON_PLUS",
    "BUILD_BUTTON_IMAGE", "TRAIN_BUTTON_IMAGE",
    "END_TURN_BUTTON_IMAGE", "SEASON_ICON_SUMMER",
]

# Layout file format. v2 added the fourth (blank) tab; older files get it filled in on load.
LAYOUT_VERSION = 2
ADDED_IN_V2 = ["TAB_EXTRA_ASSEMBLY"]

# Tabs are assembled from three sprites (left / stretched mid / right) plus a text label.
# Measured from the in-game screenshot: all four tabs unselected, 25px tall.
TAB_DEFS = {
    "TAB_ARMY_ASSEMBLY":   {"label": "Army",   "width": 84, "selected": False},
    "TAB_TOWN_ASSEMBLY":   {"label": "Town",   "width": 80, "selected": False},
    "TAB_AGENTS_ASSEMBLY": {"label": "Agents", "width": 86, "selected": False},
    "TAB_EXTRA_ASSEMBLY":  {"label": "",       "width": 83, "selected": False},
}

# ---- "In-game look" preview extras (not part of the saved layout) ----
PREVIEW_BG = "#000000"                 # the game draws black behind the HUD when no map is loaded
MINIMAP_RECT = (0, 600, 256, 168)      # black minimap box: x, y, w, h
MINIMAP_CAPITAL = (245, 625)           # the pillar capital overlaps the box from x=245 down to y=625
INCOME_TEXT_POS = (888, 665)           # "5000 (+107)"
DATE_TEXT_POS = (888, 683)             # "270 BC"
ARROW_LEFT_POS = (864, 628)
ARROW_RIGHT_POS = (994, 626)
COIN_POS = (865, 666)


def ensure_output_dir():
    """Create this launch's output folder if needed and return its path."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return OUTPUT_DIR


def output_path(filename):
    return os.path.join(ensure_output_dir(), filename)


def find_startup_layout():
    """Newest layout from a previous launch's output folder (else the legacy file)."""
    found = glob.glob(os.path.join(SCRIPT_DIR, "output_*", LAYOUT_FILENAME))
    found = [p for p in found if os.path.dirname(p) != OUTPUT_DIR]
    if found:
        return max(found, key=os.path.getmtime)
    return LEGACY_LAYOUT_FILE if os.path.exists(LEGACY_LAYOUT_FILE) else None


def dialog_start_dir():
    """Where open/load dialogs should start: this launch's folder if it exists, else the newest one."""
    if os.path.isdir(OUTPUT_DIR):
        return OUTPUT_DIR
    dirs = [d for d in glob.glob(os.path.join(SCRIPT_DIR, "output_*")) if os.path.isdir(d)]
    return max(dirs, key=os.path.getmtime) if dirs else SCRIPT_DIR


class _LazyOutputFileHandler(logging.FileHandler):
    """File handler that creates the output folder + log file only when the
    first record is actually written."""

    def __init__(self):
        super().__init__(os.path.join(OUTPUT_DIR, LOG_FILENAME), mode="w", delay=True)

    def _open(self):
        ensure_output_dir()
        return super()._open()


def setup_logging():
    handler = _LazyOutputFileHandler()
    handler.setLevel(logging.WARNING)  # an *error* log: only warnings and errors create the file
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
