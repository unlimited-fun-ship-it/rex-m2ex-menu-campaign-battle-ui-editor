#!/usr/bin/env python3
"""Undoable edits and the selected-element properties panel."""

from PyQt5.QtWidgets import QMessageBox

import config
from commands import MoveCommand, SetLayoutCommand, CropCommand

W, H = config.CANVAS_W, config.CANVAS_H


class EditMixin:
    def on_items_moved(self, moves):
        self.undo_stack.push(MoveCommand(self, moves))

    def nudge(self, dx, dy):
        moves = []
        for item in self.selected_hud_items():
            old = self.layout[item.name]
            moves.append((item.name, old, (old[0] + dx, old[1] + dy)))
        if moves:
            self.undo_stack.push(MoveCommand(self, moves, "Nudge", cid=2))

    def apply_positions(self, moves, forward):
        for name, old, new in moves:
            pos = new if forward else old
            self.layout[name] = pos
            item = self.items.get(name)
            if item and (int(item.x()), int(item.y())) != pos:
                item.setPos(*pos)
        self.refresh_props()

    def set_layout(self, layout):
        self.layout = dict(layout)
        self.rebuild()

    def apply_crop(self, sprite, crop):
        sprite.crop = crop
        self.refresh_row(sprite)
        self.rebuild()
        self.update_title()

    def add_from_browser(self, item):
        name = self.table.item(item.row(), 1).text()
        if name in self.layout:
            self.select_names([name])
            return
        c = self.view.mapToScene(self.view.viewport().rect().center())
        x = max(0, min(W - 10, int(c.x())))
        y = max(0, min(H - 10, int(c.y())))
        new = dict(self.layout)
        new[name] = (x, y)
        self.undo_stack.push(SetLayoutCommand(self, self.layout, new, f"Add {name}"))
        self.select_names([name])

    def remove_selected(self):
        names = [i.name for i in self.selected_hud_items()]
        if not names:
            return
        new = {k: v for k, v in self.layout.items() if k not in names}
        self.undo_stack.push(SetLayoutCommand(self, self.layout, new, "Remove element(s)"))

    def reset_layout(self):
        if QMessageBox.question(self, "Reset", "Reset the layout to the defaults?") == QMessageBox.Yes:
            self.undo_stack.push(
                SetLayoutCommand(self, self.layout, dict(config.DEFAULT_LAYOUT), "Reset layout"))

    @staticmethod
    def _set_spin(spin, value):
        spin.blockSignals(True)
        spin.setValue(value)
        spin.blockSignals(False)

    def refresh_props(self):
        items = self.selected_hud_items()
        self.props.setEnabled(bool(items))
        if not items:
            self.name_label.setText("-")
            self.source_label.setText("-")
            return
        single = items[0] if len(items) == 1 else None
        for s in (self.px, self.py):
            s.setEnabled(single is not None)
        crop_ok = bool(single and single.sprite)
        for s in (self.cx, self.cy, self.cw, self.ch):
            s.setEnabled(crop_ok)
        if single is None:
            self.name_label.setText(f"{len(items)} items selected")
            self.source_label.setText("-")
            return
        self.name_label.setText(single.name)
        if single.sprite:
            self.source_label.setText(single.sprite.owner.basename)
        else:
            self.source_label.setText("Assembled tab" if single.name in config.TAB_DEFS else "Not found in XMLs")
        x, y = self.layout.get(single.name, (0, 0))
        self._set_spin(self.px, x)
        self._set_spin(self.py, y)
        if single.sprite:
            for spin, v in zip((self.cx, self.cy, self.cw, self.ch), single.sprite.crop):
                self._set_spin(spin, v)

    def on_pos_spin(self):
        items = self.selected_hud_items()
        if len(items) != 1:
            return
        name = items[0].name
        new = (self.px.value(), self.py.value())
        old = self.layout[name]
        if new != old:
            self.undo_stack.push(MoveCommand(self, [(name, old, new)], "Move", cid=2))

    def on_crop_spin(self):
        items = self.selected_hud_items()
        if len(items) != 1 or not items[0].sprite:
            return
        s = items[0].sprite
        new = (self.cx.value(), self.cy.value(), self.cw.value(), self.ch.value())
        if new != s.crop:
            self.undo_stack.push(CropCommand(self, s, s.crop, new))
