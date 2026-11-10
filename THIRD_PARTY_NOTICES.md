# 第三方组件

NewXKY V3.0.1 为独立桌面程序。区域 OCR、题库匹配和激活计时都在本机完成；授权服务端使用 Python 标准库和 cryptography。第三方组件：

- PySide6 Essentials / Qt for Python：LGPLv3 / GPLv3 / 商业许可，https://doc.qt.io/qtforpython-6/licenses.html
- RapidOCR 及随附 OCR 模型：Apache-2.0，https://github.com/RapidAI/RapidOCR
- ONNX Runtime：MIT，https://github.com/microsoft/onnxruntime
- OpenCV：Apache-2.0，https://github.com/opencv/opencv
- Pillow：HPND，https://github.com/python-pillow/Pillow
- NumPy：BSD-3-Clause，https://numpy.org/
- cryptography：Apache-2.0 / BSD-3-Clause 双许可，https://cryptography.io/
- PyInstaller：GPL 及分发例外，https://pyinstaller.org/en/stable/license.html
- pdfplumber（仅题库构建工具，不随客户端打包）：MIT，https://github.com/jsvine/pdfplumber
- openpyxl（仅验证码生成/分发工具，不随客户端打包）：MIT，https://openpyxl.readthedocs.io/

分发时请保留运行库中的许可文件，并遵守各依赖的许可要求。
