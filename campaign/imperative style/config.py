#!/usr/bin/env python3
"""
Configuration, constants, and logging setup.
"""

import os
import logging
from datetime import datetime

# Setup Directories
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NOW_STR = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, f"output_{NOW_STR}")
HUD_LAYOUTS_DIR = os.path.join(SCRIPT_DIR, "hud_layouts")
LAYOUT_SAVE_FILE = os.path.join(SCRIPT_DIR, "hud_layout.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(HUD_LAYOUTS_DIR, exist_ok=True)

# Setup Logging
LOG_FILE = os.path.join(OUTPUT_DIR, "editor_log.txt")
logging.basicConfig(
    filename=LOG_FILE, 
    level=logging.DEBUG, 
    format='%(asctime)s - %(levelname)s - %(message)s', 
    filemode='w'
)
logging.info(f"Starting RTW Campaign HUD Editor. Outputs will be saved to: {OUTPUT_DIR}")

# Default Layouts and Orders
DEFAULT_LAYOUT = {
    "STRAT_HUD_LEFT": (0, 587),
    "STRAT_HUD_MIDDLE": (281, 621),
    "STRAT_HUD_RIGHT": (743, 587),
    "TAB_ARMY_ASSEMBLY": (284, 587),
    "TAB_TOWN_ASSEMBLY": (354, 587),
    "TAB_AGENTS_ASSEMBLY": (424, 587),
    "RADAR_BUTTON_MINUS": (32, 715), 
    "RADAR_BUTTON_PLUS": (52, 715),
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
    "END_TURN_BUTTON_IMAGE", "SEASON_ICON_SUMMER"
]