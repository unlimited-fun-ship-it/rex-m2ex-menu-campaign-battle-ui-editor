#!/usr/bin/env python3
"""REX Campaign HUD Editor - the main window.

The window itself only owns the shared state and wires the pieces together;
the behaviour lives in the mixins:

  ui_panels.py      widget construction (top bar, browser, right panel)
  ui_menus.py       menu bar
  game_data.py      game folder / .sd.xml loading / texture table
  scene_builder.py  building the graphics scene
  edit_actions.py   undoable edits + properties panel
  persistence.py    layout / XML saving, PNG export, screenshots
  commands.py       undo commands
"""

import os
import logging

from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import QMainWindow, QGraphicsScene, QMessageBox, QUndoStack

import config
from assets import AssetManager
from canvas import HudView
from ui_panels import PanelsMixin
from ui_menus import MenusMixin
from game_data import GameDataMixin
from scene_builder import SceneMixin
from edit_actions import EditMixin
from persistence import PersistenceMixin

log = logging.getLogger(__name__)
W, H = config.CANVAS_W, config.CANVAS_H


class MainWindow(PanelsMixin, MenusMixin, GameDataMixin, SceneMixin, EditMixin,
                 PersistenceMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("REXUiEditor", "CampaignHud")
        self.assets = AssetManager()
        self.game_root = ""
        self.sd_files = []
        self.sprites = {}                       # name -> Sprite (first definition wins)
        self.layout = dict(config.DEFAULT_LAYOUT)
        self.layout_path = None   # None = default: <this launch's output folder>/hud_layout.json
        self.items = {}                         # name -> HudItem
        self.bg_path, self.bg_opacity, self.bg_fade = None, 100, 0
        self.bg_item = None
        self.ref_path, self.ref_item = None, None
        self.undo_stack = QUndoStack(self)

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, W, H)
        self.view = HudView(self.scene)
        self.view.setBackgroundBrush(QBrush(QColor("#1e1e1e")))

        self._build_ui()
        self._build_menus()

        self.scene.selectionChanged.connect(self.refresh_props)
        self.view.nudge.connect(self.nudge)
        self.undo_stack.cleanChanged.connect(self.update_title)
        self.undo_stack.indexChanged.connect(self.update_title)

        self.resize(1600, 950)
        self.update_title()
        startup = config.find_startup_layout()
        if startup:
            self._load_layout_file(startup, quiet=True)
        self.rebuild()

        last = self.settings.value("game_root", "")
        if last and os.path.isdir(os.path.join(last, "data")):
            self.set_game_root(last)

    def update_title(self, *_):
        star = "*" if self.has_unsaved() else ""
        name = os.path.basename(self.layout_path) if self.layout_path else "unsaved layout"
        self.setWindowTitle(f"REX Campaign HUD Editor - {name}{star}")

    def has_unsaved(self):
        return (not self.undo_stack.isClean()) or any(f.dirty for f in self.sd_files)

    def closeEvent(self, event):
        if not self.has_unsaved():
            event.accept()
            return
        r = QMessageBox.question(
            self, "Unsaved changes", "Save the layout before quitting?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            event.ignore()
        else:
            if r == QMessageBox.Save and not self.save_layout():
                event.ignore()
                return
            event.accept()
