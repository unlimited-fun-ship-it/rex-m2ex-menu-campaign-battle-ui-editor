#!/usr/bin/env python3
"""Graphics items and the zoomable view."""

from PyQt5.QtCore import Qt, QPointF, pyqtSignal
from PyQt5.QtGui import QPen, QColor, QPainter
from PyQt5.QtWidgets import (
    QGraphicsPixmapItem, QGraphicsView, QStyle, QStyleOptionGraphicsItem,
)


class HudItem(QGraphicsPixmapItem):
    """A single draggable HUD element. The pixmap *is* the item, so the image
    and its hit-box can never drift apart."""

    dragging = False  # class-wide: snap only while the user drags

    def __init__(self, name, pixmap, sprite, on_moved, snap_getter):
        super().__init__(pixmap)
        self.name = name
        self.sprite = sprite          # may be None (tabs / missing sprites)
        self._on_moved = on_moved     # callback(list[(name, old, new)])
        self._snap = snap_getter
        self._origins = {}
        self.setShapeMode(QGraphicsPixmapItem.BoundingRectShape)
        self.setFlag(QGraphicsPixmapItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsPixmapItem.ItemSendsGeometryChanges, True)

    def set_movable(self, movable):
        self.setFlag(QGraphicsPixmapItem.ItemIsMovable, movable)
        self.setCursor(Qt.OpenHandCursor if movable else Qt.ArrowCursor)

    def itemChange(self, change, value):
        if change == QGraphicsPixmapItem.ItemPositionChange and HudItem.dragging:
            s = max(1, self._snap())
            return QPointF(round(value.x() / s) * s, round(value.y() / s) * s)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            HudItem.dragging = True
            self._origins = {
                i: i.pos() for i in self.scene().selectedItems() if isinstance(i, HudItem)
            }

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        HudItem.dragging = False
        moves = []
        for item, old in self._origins.items():
            new = item.pos()
            if new != old:
                moves.append((item.name, (int(old.x()), int(old.y())), (int(new.x()), int(new.y()))))
        self._origins = {}
        if moves:
            self._on_moved(moves)

    def paint(self, painter, option, widget=None):
        opt = QStyleOptionGraphicsItem(option)
        opt.state &= ~QStyle.State_Selected  # we draw our own outline
        super().paint(painter, opt, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor("red"), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(0, 0, -1, -1))


class HudView(QGraphicsView):
    nudge = pyqtSignal(int, int)

    def __init__(self, scene):
        super().__init__(scene)
        self.auto_fit = True
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFocusPolicy(Qt.StrongFocus)

    def fit_all(self):
        self.auto_fit = True
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def zoom_100(self):
        self.auto_fit = False
        self.resetTransform()

    def zoom_by(self, factor):
        self.auto_fit = False
        current = self.transform().m11()
        if 0.2 <= current * factor <= 16:
            self.scale(factor, factor)

    def wheelEvent(self, event):
        self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.auto_fit:
            self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def keyPressEvent(self, event):
        step = 10 if event.modifiers() & Qt.ShiftModifier else 1
        deltas = {Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0),
                  Qt.Key_Up: (0, -step), Qt.Key_Down: (0, step)}
        if event.key() in deltas:
            self.nudge.emit(*deltas[event.key()])
            event.accept()
        else:
            super().keyPressEvent(event)
