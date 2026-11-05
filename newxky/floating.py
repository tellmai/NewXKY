from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget


class FloatingAnswer(QWidget):
    expand = Signal()
    toggle = Signal()
    auto_toggle = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NewXKY · 悬浮答案")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.resize(360, 330)
        self.setMinimumSize(300, 250)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        self.answer = QLabel("—")
        self.answer.setObjectName("answer")
        self.answer.setTextFormat(Qt.PlainText)
        layout.addWidget(self.answer)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.RichText)
        layout.addWidget(self.message)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.PlainText)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(self.detail)
        layout.addWidget(area, 1)
        self.toggle_button = QPushButton("开始识别")
        self.toggle_button.clicked.connect(self.toggle.emit)
        layout.addWidget(self.toggle_button)
        self.auto_button = QPushButton("启动自动答题")
        self.auto_button.clicked.connect(self.auto_toggle.emit)
        layout.addWidget(self.auto_button)
        expand_button = QPushButton("展开主界面")
        expand_button.clicked.connect(self.expand.emit)
        layout.addWidget(expand_button)

    def closeEvent(self, event):
        self.expand.emit()
        event.accept()
