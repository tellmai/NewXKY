"""Model-backed transfers between the personnel pool and waiting queue."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget,QAbstractItemView


class RosterList(QListWidget):
    transfer_requested = Signal(object,int)

    def __init__(self, *, reorder=False):
        super().__init__()
        self.peer = None
        self.reorder = reorder
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)

    def dragEnterEvent(self,event):
        if self.peer is not None and event.source() is self.peer and self.isEnabled() and self.peer.isEnabled():
            event.setDropAction(Qt.CopyAction)
            event.accept()
        elif event.source() is self and self.reorder:
            super().dragEnterEvent(event)
        else:
            event.ignore()

    def dragMoveEvent(self,event):
        if self.peer is not None and event.source() is self.peer and self.isEnabled() and self.peer.isEnabled():
            super().dragMoveEvent(event)
            event.setDropAction(Qt.CopyAction)
            event.accept()
        elif event.source() is self and self.reorder:
            super().dragMoveEvent(event)
        else:
            event.ignore()

    def dropEvent(self,event):
        if self.peer is not None and event.source() is self.peer and self.isEnabled() and self.peer.isEnabled():
            rows = [item.data(Qt.UserRole) for item in self.peer.selectedItems()]
            item = self.itemAt(event.position().toPoint())
            position = self.row(item) if item is not None else self.count()
            if item is not None and self.dropIndicatorPosition() == QAbstractItemView.BelowItem:
                position += 1
            if not rows:
                event.ignore()
                return
            # The owner updates both lists from its queue. CopyAction prevents
            # Qt from deleting another source row after the refreshed drop.
            self.transfer_requested.emit(rows,position)
            event.setDropAction(Qt.CopyAction)
            event.accept()
        elif event.source() is self and self.reorder and self.isEnabled():
            super().dropEvent(event)
        else:
            event.ignore()
