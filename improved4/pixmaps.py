#!/usr/bin/env python3
"""Small QPixmap/QImage helpers used when building the scene."""

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QFont, QPixmap, QImage, QPainter


def blank_pixmap(w, h, fill=Qt.transparent):
    img = QImage(max(1, w), max(1, h), QImage.Format_ARGB32_Premultiplied)
    img.fill(fill)
    return img


def placeholder_pixmap(w, h, label):
    img = blank_pixmap(max(w, 24), max(h, 14), QColor(255, 0, 255, 90))
    p = QPainter(img)
    p.setPen(QColor("white"))
    p.setFont(QFont("Arial", 6))
    p.drawText(QRectF(0, 0, img.width(), img.height()), Qt.AlignCenter | Qt.TextWordWrap, label)
    p.end()
    return QPixmap.fromImage(img)
