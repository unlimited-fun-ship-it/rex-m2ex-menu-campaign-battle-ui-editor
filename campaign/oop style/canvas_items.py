#!/usr/bin/env python3
"""
Custom PyQt5 QGraphicsItems for the canvas.
"""

from PyQt5.QtWidgets import QGraphicsRectItem
from PyQt5.QtCore import Qt

class DraggableSprite(QGraphicsRectItem):
    def __init__(self, x, y, w, h, sprite_name, update_callback):
        super().__init__(x, y, w, h)
        self.sprite_name = sprite_name
        self.update_callback = update_callback
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        # When the user releases the mouse, update the backend layout dictionary
        new_x = int(self.pos().x())
        new_y = int(self.pos().y())
        self.update_callback(self.sprite_name, new_x, new_y)