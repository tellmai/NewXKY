from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRegion
from PySide6.QtWidgets import QWidget


class RegionSelector(QWidget):
    selected = Signal(object)
    cancelled = Signal()

    def __init__(self, screen):
        super().__init__()
        self._screen = screen
        self._background = screen.grabWindow(0)
        self._origin = None
        self._selection = QRect()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._background)
        painter.fillRect(self.rect(), QColor(7, 16, 31, 150))
        if not self._selection.isEmpty():
            painter.save()
            painter.setClipRect(self._selection)
            painter.drawPixmap(self.rect(), self._background)
            painter.restore()
            painter.setPen(QPen(QColor("#43dfbb"), 2))
            painter.drawRect(self._selection.adjusted(0, 0, -1, -1))
        painter.setFont(QFont("Microsoft YaHei UI", 13))
        painter.setPen(QColor("white"))
        painter.drawText(QRect(24, 24, self.width() - 48, 100), Qt.TextWordWrap,
                         "拖动框选题干和选项；自动答题还需框入底部上一题 / 下一题 / 提交按钮\n请避开计时器及答案窗口 · Esc / 右键取消 · 区域限于一块显示器")

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.cancelled.emit()
        elif event.button() == Qt.LeftButton:
            self._origin = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self._origin is not None:
            point = event.position().toPoint()
            point = QPoint(max(0, min(self.width() - 1, point.x())), max(0, min(self.height() - 1, point.y())))
            self._selection = QRect(self._origin, point).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._origin is not None:
            self.mouseMoveEvent(event)
            if self._selection.width() >= 120 and self._selection.height() >= 80:
                self.selected.emit(QRect(self.mapToGlobal(self._selection.topLeft()), self._selection.size()))
            else:
                self._origin = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()


class RegionBorder(QWidget):
    """Only pixels OUTSIDE the captured rectangle are ever painted."""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def set_region(self, rect):
        self.setGeometry(rect.adjusted(-3, -3, 3, 3))
        self.setMask(QRegion(self.rect()).subtracted(QRegion(self.rect().adjusted(3, 3, -3, -3))))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(QColor("#10b897"), 2))
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
