#!/usr/bin/env python3
"""Loading the game folder, the .sd.xml files and the texture browser table."""

import os
import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QApplication

import config
import sd_xml

log = logging.getLogger(__name__)


class GameDataMixin:
    def select_game_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Game Root Folder", self.game_root)
        if not folder:
            return
        if not os.path.isdir(os.path.join(folder, "data")):
            QMessageBox.warning(self, "Not a game folder", "That folder has no 'data' subfolder.")
            return
        self.set_game_root(folder)

    def set_game_root(self, folder):
        self.game_root = folder
        self.settings.setValue("game_root", folder)
        self.folder_entry.setText(folder)
        self.load_game_data()

    def load_game_data(self):
        if not self.game_root:
            return
        culture = self.culture_combo.currentText()
        self.assets.configure(self.game_root, culture)
        self.sd_files, self.sprites = [], {}
        missing = []
        for name in config.REQUIRED_XMLS:
            path = sd_xml.locate_xml(self.game_root, culture, name)
            if not path:
                missing.append(name)
                continue
            try:
                f = sd_xml.SdFile(path)
            except Exception as e:
                log.exception("Failed to parse %s", path)
                missing.append(f"{name} (parse error: {e})")
                continue
            self.sd_files.append(f)
            for s in f.sprites:
                self.sprites.setdefault(s.name, s)

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.populate_table()
            self.rebuild()
        finally:
            QApplication.restoreOverrideCursor()

        if self.sd_files:
            msg = f"Loaded {len(self.sd_files)} HUD files, {len(self.sprites)} sprites."
            if missing:
                msg += f" Missing: {', '.join(missing)}"
            self.status_label.setText(msg)
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText("Error: no HUD XMLs found.")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")

    def populate_table(self):
        t = self.table
        t.setSortingEnabled(False)
        t.setRowCount(0)
        all_sprites = [s for f in self.sd_files for s in f.sprites]
        t.setRowCount(len(all_sprites))
        for row, s in enumerate(all_sprites):
            self._fill_row(row, s)
        t.setSortingEnabled(True)
        t.setColumnWidth(1, 180)
        self.filter_table()

    def _fill_row(self, row, s):
        t = self.table
        icon_item = QTableWidgetItem()
        icon_item.setIcon(self.assets.sprite_icon(s))
        t.setItem(row, 0, icon_item)
        t.setItem(row, 1, QTableWidgetItem(s.name))
        t.setItem(row, 2, QTableWidgetItem(s.owner.basename))
        for col, v in zip((3, 4, 5, 6), s.crop):
            it = QTableWidgetItem()
            it.setData(Qt.DisplayRole, v)
            t.setItem(row, col, it)

    def refresh_row(self, sprite):
        t = self.table
        t.setSortingEnabled(False)
        for row in range(t.rowCount()):
            if t.item(row, 1).text() == sprite.name and t.item(row, 2).text() == sprite.owner.basename:
                self._fill_row(row, sprite)
        t.setSortingEnabled(True)

    def filter_table(self, *_):
        needle = self.search.text().strip().lower()
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 1).text().lower()
            self.table.setRowHidden(row, bool(needle) and needle not in name)
