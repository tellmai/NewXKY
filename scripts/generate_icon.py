"""Render the source vector into a multi-resolution Windows executable icon."""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "tmp" / "icon-preview.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(root / "assets" / "NewXKY.svg"))
    if not renderer.isValid():
        raise ValueError("Application icon SVG is invalid")
    image = QImage(512, 512, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    if not image.save(str(output)):
        raise OSError("Application icon preview could not be saved")
    icon_path = root / "assets" / "NewXKY.ico"
    with Image.open(output) as pixels:
        pixels.save(icon_path, format="ICO", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    print(icon_path)


if __name__ == "__main__":
    main()
