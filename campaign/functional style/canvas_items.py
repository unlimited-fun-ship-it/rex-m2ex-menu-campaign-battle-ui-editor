#!/usr/bin/env python3
"""
Custom PyQt5 QGraphicsItems.
"""

from PyQt5.QtWidgets import QGraphicsRectItem

class DraggableSprite(QGraphicsRectItem):
    def __init__(self, x, y, w, h, sprite_name, update_callback):
        super().__init__(x, y, w, h)
        self.sprite_name = sprite_name
        self.update_callback = update_callback
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        # Passes new coordinates to a pure function via callback
        self.update_callback(self.sprite_name, int(self.pos().x()), int(self.pos().y()))