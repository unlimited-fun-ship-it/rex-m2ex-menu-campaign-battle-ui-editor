#!/usr/bin/env python3
"""Saving/loading layouts and XML crops; PNG export and screenshots."""

import os
import json
import logging
from datetime import datetime

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QFileDialog, QMessageBox

import config
from commands import SetLayoutCommand

log = logging.getLogger(__name__)
W, H = config.CANVAS_W, config.CANVAS_H


class PersistenceMixin:
    def _layout_to_json(self, path):
        with open(path, "w") as f:
            json.dump({"_version": config.LAYOUT_VERSION, **{k: list(v) for k, v in self.layout.items()}}, f, indent=4)

    def save_layout(self):
        try:
            main = self.layout_path or config.output_path(config.LAYOUT_FILENAME)
            self._layout_to_json(main)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._layout_to_json(config.output_path(f"hud_layout_{stamp}.json"))
        except Exception as ex:
            log.exception("Could not save layout")
            QMessageBox.critical(self, "Error", f"Could not save layout:\n{ex}")
            return False
        self.undo_stack.setClean()
        self.update_title()
        self.statusBar().showMessage(f"Saved {main} (+ timestamped copy in {config.OUTPUT_DIR})", 5000)
        return True

    def save_layout_as(self):
        start = config.output_path(config.LAYOUT_FILENAME)
        path, _ = QFileDialog.getSaveFileName(self, "Save Layout As", start, "JSON (*.json)")
        if path:
            self.layout_path = path
            return self.save_layout()
        return False

    def _load_layout_file(self, path, quiet=False):
        if not os.path.exists(path):
            return False
        try:
            with open(path) as f:
                data = json.load(f)
            layout = {str(k): (int(v[0]), int(v[1])) for k, v in data.items() if not str(k).startswith("_")}
            if int(data.get("_version", 1)) < config.LAYOUT_VERSION:
                for k in config.ADDED_IN_V2:      # elements added since the file was written
                    layout.setdefault(k, config.DEFAULT_LAYOUT[k])
        except Exception as e:
            log.exception("Could not load layout")
            if not quiet:
                QMessageBox.critical(self, "Error", f"Could not load layout:\n{e}")
            return False
        self.layout = layout
        return True

    def load_layout_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Layout", config.dialog_start_dir(), "JSON (*.json)")
        if not path:
            return
        old = dict(self.layout)
        if self._load_layout_file(path):
            new = self.layout
            self.layout = old  # let the command perform the swap so it is undoable
            self.undo_stack.push(SetLayoutCommand(self, old, new, "Load layout"))
            self.update_title()

    def save_all_xmls(self):
        dirty = [f for f in self.sd_files if f.dirty]
        if not dirty:
            QMessageBox.information(self, "Nothing to save", "No crop rectangles have been changed.")
            return
        try:
            for f in dirty:
                f.save()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")
            return
        self.update_title()
        QMessageBox.information(
            self, "Saved",
            "Saved crop changes to:\n" + "\n".join(f.basename for f in dirty) +
            "\n\nThe first save keeps the original as <file>.bak")

    def export_png(self):
        prev = [i.name for i in self.selected_hud_items()]
        self.scene.clearSelection()
        img = QImage(W, H, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        self.scene.render(p, QRectF(0, 0, W, H), QRectF(0, 0, W, H))
        p.end()
        self.select_names(prev)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save HUD Image", config.output_path("campaign_hud_preview.png"),
            "PNG Image (*.png)")
        if path and img.save(path):
            self.statusBar().showMessage(f"Exported {path}", 5000)

    def screenshot(self):
        name = f"program_screenshot_{datetime.now().strftime('%H%M%S')}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Program Screenshot", config.output_path(name), "PNG Image (*.png)")
        if path:
            self.grab().save(path)
