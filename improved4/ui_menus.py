#!/usr/bin/env python3
"""Menu bar and status-bar hint."""

from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QAction


class MenusMixin:
    def _build_menus(self):
        def act(menu, text, slot, shortcut=None):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        m = self.menuBar().addMenu("&File")
        act(m, "Open Game Folder...", self.select_game_folder, QKeySequence.Open)
        m.addSeparator()
        act(m, "Save Layout", self.save_layout, QKeySequence.Save)
        act(m, "Save Layout As...", self.save_layout_as, QKeySequence("Ctrl+Shift+S"))
        act(m, "Load Layout...", self.load_layout_dialog, QKeySequence("Ctrl+L"))
        m.addSeparator()
        act(m, "Save Crop Changes to XML", self.save_all_xmls)
        act(m, "Export HUD as PNG...", self.export_png, QKeySequence("Ctrl+E"))
        act(m, "Screenshot Program UI...", self.screenshot)
        m.addSeparator()
        act(m, "Quit", self.close, QKeySequence.Quit)

        m = self.menuBar().addMenu("&Edit")
        undo = self.undo_stack.createUndoAction(self, "&Undo")
        undo.setShortcut(QKeySequence.Undo)
        redo = self.undo_stack.createRedoAction(self, "&Redo")
        redo.setShortcut(QKeySequence.Redo)
        m.addAction(undo)
        m.addAction(redo)
        m.addSeparator()
        act(m, "Remove Selected from HUD", self.remove_selected, QKeySequence.Delete)
        act(m, "Select All", lambda: [i.setSelected(True) for i in self.items.values()],
            QKeySequence.SelectAll)
        act(m, "Reset Layout to Default", self.reset_layout)

        m = self.menuBar().addMenu("&View")
        act(m, "Zoom In", lambda: self.view.zoom_by(1.25), QKeySequence.ZoomIn)
        act(m, "Zoom Out", lambda: self.view.zoom_by(0.8), QKeySequence.ZoomOut)
        act(m, "Actual Size (100%)", self.view.zoom_100, QKeySequence("Ctrl+0"))
        act(m, "Fit to Window", self.view.fit_all, QKeySequence("Ctrl+9"))

        self.statusBar().showMessage(
            "Wheel = zoom | drag = move | arrows = nudge 1px (Shift = 10px) | Ctrl+Z = undo")
