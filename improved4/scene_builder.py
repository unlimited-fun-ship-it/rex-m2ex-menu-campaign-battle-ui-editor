#!/usr/bin/env python3
"""Building the graphics scene: HUD items, tabs, minimap and background image."""

import os
import logging

from PIL import Image, ImageChops
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QBrush, QPen, QFont, QPixmap, QPainter
from PyQt5.QtWidgets import QFileDialog

import config
from assets import pil_to_pixmap, LANCZOS
from canvas import HudItem
from pixmaps import blank_pixmap, placeholder_pixmap

log = logging.getLogger(__name__)
W, H = config.CANVAS_W, config.CANVAS_H


class SceneMixin:
    def selected_hud_items(self):
        return [i for i in self.scene.selectedItems() if isinstance(i, HudItem)]

    def select_names(self, names):
        self.scene.blockSignals(True)
        self.scene.clearSelection()
        for n in names:
            if n in self.items:
                self.items[n].setSelected(True)
        self.scene.blockSignals(False)
        self.refresh_props()

    def _tab_pixmap(self, key):
        d = config.TAB_DEFS[key]
        label, selected, total_w = d["label"], d["selected"], d["width"]
        sfx = "_SELECTED" if selected else ""
        parts = [self.sprites.get(f"HUD_TEXT_TAB_{p}{sfx}") for p in ("LEFT", "MID", "RIGHT")]
        left, mid, right = [self.assets.sprite_pixmap(s) if s else None for s in parts]
        if not (left and mid and right):
            return placeholder_pixmap(total_w, 25, label)
        h = max(left.height(), mid.height(), right.height())
        img = blank_pixmap(total_w, h)
        p = QPainter(img)
        p.drawPixmap(0, 0, left)
        mid_w = max(1, total_w - left.width() - right.width())
        p.drawPixmap(left.width(), 0, mid.scaled(mid_w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        p.drawPixmap(total_w - right.width(), 0, right)
        if label:
            font = QFont("Tahoma")
            font.setPixelSize(11)
            p.setFont(font)
            p.setPen(QColor("#000000" if selected else "#6e6e72"))  # unselected labels look faded in-game
            p.drawText(QRectF(0, 0, total_w, h - 4), Qt.AlignCenter, label)
        p.end()
        return QPixmap.fromImage(img)

    def _item_pixmap(self, name):
        if name in config.TAB_DEFS:
            return self._tab_pixmap(name), None
        s = self.sprites.get(name)
        if s:
            pm = self.assets.sprite_pixmap(s)
            return (pm or placeholder_pixmap(s.w, s.h, name)), s
        return placeholder_pixmap(48, 24, name), None

    def _z_for(self, name, index):
        if name in config.BACKGROUNDS:
            return config.BACKGROUNDS.index(name) * 0.01
        if name in config.DRAW_ORDER:
            return 10 + config.DRAW_ORDER.index(name)
        if name in config.TAB_DEFS:
            return 20
        return 30 + index

    def rebuild(self):
        keep = [i.name for i in self.selected_hud_items()]
        self.scene.blockSignals(True)
        self.scene.clear()
        self.items.clear()
        self.bg_item = None

        self.ref_item = None
        base = self.scene.addRect(0, 0, W, H, QPen(Qt.NoPen), QBrush(QColor(config.PREVIEW_BG)))
        base.setZValue(-200)
        self.update_background()
        self._add_extras()

        for idx, (name, (x, y)) in enumerate(self.layout.items()):
            pm, sprite = self._item_pixmap(name)
            item = HudItem(name, pm, sprite, self.on_items_moved, self.snap_spin.value)
            item.setPos(x, y)
            item.setZValue(self._z_for(name, idx))
            self.scene.addItem(item)
            self.items[name] = item

        self.apply_flags()
        self.update_reference()
        self.scene.blockSignals(False)
        self.select_names(keep)

    def apply_flags(self, *_):
        builder = self.chk_builder.isChecked()
        lock_bg = self.chk_lock_bg.isChecked()
        for name, item in self.items.items():
            item.set_movable(builder and not (lock_bg and name in config.BACKGROUNDS))

    def update_background(self):
        if self.bg_item is not None:
            self.scene.removeItem(self.bg_item)
            self.bg_item = None
        if not self.bg_path or not os.path.exists(self.bg_path):
            return
        try:
            img = Image.open(self.bg_path).convert("RGBA").resize((W, H), LANCZOS)
            alpha = img.getchannel("A").point(lambda p: int(p * self.bg_opacity / 100.0))
            if self.bg_fade > 0:
                fh = max(1, int(H * self.bg_fade / 100.0))
                mask = Image.new("L", (W, H), 255)
                mask.paste(Image.linear_gradient("L").resize((W, fh)), (0, 0))
                alpha = ImageChops.multiply(alpha, mask)
            img.putalpha(alpha)
            self.bg_item = self.scene.addPixmap(pil_to_pixmap(img))
            self.bg_item.setZValue(-100)
        except Exception:
            log.exception("Background image failed")

    def load_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Background Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.tga)")
        if path:
            self.bg_path = path
            self.update_background()

    def on_bg_sliders(self):
        self.bg_opacity = self.opacity_slider.value()
        self.bg_fade = self.fade_slider.value()
        self.update_background()

    # ------------------------------------------------- in-game look extras
    def _sprite_startswith(self, prefix, size=None):
        found = [s for n, s in self.sprites.items() if n.startswith(prefix)]
        if size:
            exact = [s for s in found if (s.w, s.h) == size]
            found = exact or found
        return found[0] if found else None

    def _sprite_containing(self, words):
        for w in words:
            for n, s in self.sprites.items():
                if w in n:
                    return s
        return None

    def _add_extras(self):
        """Static, non-editable decoration that makes the preview look like the real game:
        black minimap box, scroll arrows, treasury/date text. Skipped if sprites are missing."""
        if not self.chk_extras.isChecked():
            return

        def static(item, z):
            item.setZValue(z)
            item.setAcceptedMouseButtons(Qt.NoButton)
            return item

        no_pen, black = QPen(Qt.NoPen), QBrush(Qt.black)
        mx, my, mw, mh = config.MINIMAP_RECT
        cx, cy = config.MINIMAP_CAPITAL
        static(self.scene.addRect(mx, my, cx - mx, mh, no_pen, black), 4)
        static(self.scene.addRect(cx, cy, mx + mw - cx, my + mh - cy, no_pen, black), 4)

        if self.chk_radar.isChecked() and self.game_root:
            mm = self.assets.minimap_pixmap((cx - mx, mh))
            if mm:
                static(self.scene.addPixmap(mm), 5).setPos(mx, my)

        for prefix, pos in (("PREV_BU", config.ARROW_LEFT_POS), ("NEXT_BU", config.ARROW_RIGHT_POS)):
            spr = self._sprite_startswith(prefix, size=(17, 31))
            pm = self.assets.sprite_pixmap(spr) if spr else None
            if pm:
                static(self.scene.addPixmap(pm), 9).setPos(*pos)

        coin = self._sprite_containing(("COIN", "TREASURY", "MONEY"))
        pm = self.assets.sprite_pixmap(coin) if coin else None
        if pm:
            static(self.scene.addPixmap(pm), 9).setPos(*config.COIN_POS)

        font = QFont("Tahoma")
        font.setPixelSize(12)
        for html, pos in (
            ('5000 <span style="color:#1e5a32">(+107)</span>', config.INCOME_TEXT_POS),
            ("270 BC", config.DATE_TEXT_POS),
        ):
            t = self.scene.addText("")
            t.document().setDocumentMargin(0)
            t.setFont(font)
            t.setDefaultTextColor(QColor("#111111"))
            t.setHtml(html)
            t.setPos(*pos)
            static(t, 9)

    # ------------------------------------------------ reference screenshot
    def load_reference(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select In-Game Screenshot", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.ref_path = path
            self.chk_ref.setChecked(True)
            self.update_reference()

    def update_reference(self, *_):
        """Semi-transparent screenshot drawn ON TOP of the HUD for aligning elements."""
        if getattr(self, "ref_item", None) is not None:
            self.scene.removeItem(self.ref_item)
            self.ref_item = None
        if not self.ref_path or not self.chk_ref.isChecked() or not os.path.exists(self.ref_path):
            return
        pm = QPixmap(self.ref_path)
        if pm.isNull():
            return
        if (pm.width(), pm.height()) == (W, H + 32):       # windowed screenshot: strip the title bar
            pm = pm.copy(0, 32, W, H)
        elif (pm.width(), pm.height()) != (W, H):
            pm = pm.scaled(W, H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self.ref_item = self.scene.addPixmap(pm)
        self.ref_item.setZValue(1000)
        self.ref_item.setOpacity(self.ref_slider.value() / 100.0)
        self.ref_item.setAcceptedMouseButtons(Qt.NoButton)
