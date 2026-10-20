#!/usr/bin/env python3
"""Undo/redo commands (QUndoCommand subclasses)."""

from PyQt5.QtWidgets import QUndoCommand


class MoveCommand(QUndoCommand):
    def __init__(self, win, moves, text="Move", cid=-1):
        super().__init__(text)
        self.win, self.moves, self.cid = win, moves, cid

    def id(self):
        return self.cid

    def mergeWith(self, other):
        if other.id() != self.cid or [m[0] for m in other.moves] != [m[0] for m in self.moves]:
            return False
        self.moves = [(n, o, nn) for (n, o, _), (_, _, nn) in zip(self.moves, other.moves)]
        return True

    def redo(self):
        self.win.apply_positions(self.moves, forward=True)

    def undo(self):
        self.win.apply_positions(self.moves, forward=False)


class SetLayoutCommand(QUndoCommand):
    """Used for add / remove / reset / load: swaps the whole layout."""

    def __init__(self, win, old, new, text):
        super().__init__(text)
        self.win, self.old, self.new = win, dict(old), dict(new)

    def redo(self):
        self.win.set_layout(self.new)

    def undo(self):
        self.win.set_layout(self.old)


class CropCommand(QUndoCommand):
    def __init__(self, win, sprite, old, new):
        super().__init__(f"Edit crop of {sprite.name}")
        self.win, self.sprite, self.old, self.new = win, sprite, old, new

    def id(self):
        return 3

    def mergeWith(self, other):
        if other.id() != 3 or other.sprite is not self.sprite:
            return False
        self.new = other.new
        return True

    def redo(self):
        self.win.apply_crop(self.sprite, self.new)

    def undo(self):
        self.win.apply_crop(self.sprite, self.old)
