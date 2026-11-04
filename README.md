# NewXKY 区域答题助手

Windows 本地桌面程序。参考 Answering-S 的 PDF 题库解析、本地 OCR 和题目内容匹配方式，实现“导入 PDF → 框选屏幕区域 → 持续显示当前题目的答案”。

Git 仓库提供源码、测试和构建脚本。首次克隆后，需要先安装 Python 3.11 或 3.12，运行 `安装依赖.cmd`，再运行 `启动软件.cmd`。题库 PDF、截图、个人运行数据、`runtime` 环境和打包文件不随源码仓库发布；题库请在软件内自行导入。

## 使用

### 免安装便携版

将 `NewXKY-portable.zip` 整包解压，双击其中的 `启动软件.cmd`。无需安装 Python，无需启动时下载 OCR 模型；题库自行导入。请保留 `runtime`、`assets`、`newxky` 等文件夹。

此便携版使用 Python 官网原始的签名运行程序。旧的 PyInstaller `dist/NewXKY/NewXKY.exe` 没有数字签名，可能被 Windows 智能应用控制阻止；便携版使用独立启动入口，不包含这个旧 exe。Windows 的信任判定以系统实际策略为准，项目不会修改安全功能。参考 [Microsoft Smart App Control 说明](https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/overview)。

如启动失败，会显示提示并将详细错误写入 `data/startup-error.log`。也可以运行 `启动并查看错误.cmd` 查看错误信息。

开发者在 Windows 上执行 `python scripts/build_portable.py` 可构建便携 ZIP。构建过程验证 Python 官方下载文件的 SHA-256 和 Authenticode 签名，从 PyPI 安装依赖，并将本地 OCR 模型一起打包。`requirements-portable.txt` 对应新版 OCR 运行环境，常规源码安装仍使用 `requirements.txt`。

1. 安装依赖后双击 `启动软件.cmd`。如本机已有 `runtime` Python 运行环境则优先使用，其次使用 `.venv`，最后使用 `dist\NewXKY\NewXKY.exe`。
2. 点击“导入 PDF 题库”，选择题库文件，可以多选。导入在后台执行，进度显示当前文件及页码。有效题目、去重数量和异常会显示在界面；异常题目不会参与匹配。
3. 打开浏览器答题页，点击“框选 / 重选区域”，拖动选择**一道题的完整题干和全部选项**。Esc 或右键取消。
4. 把浏览器中的题目放在该区域内，并将答案窗口移到区域外。点击“开始识别”。绿色边框标出检测范围，不拦截鼠标。
5. 答案区显示正确答案字母、完整选项内容和 PDF 来源页码。完整网页选项核对成功时，按**当前网页选项顺序**显示；选项没露全时，只要题干能确定唯一答案，按**题库顺序**显示并明确标注。换题、页面刷新或滚动造成画面变化后，旧答案会先清空，再识别新题。

可以暂停、重新识别、重选区域及开启窗口置顶。题库和上次选择的区域会自动保存，重新启动后无需重复导入。启动后不自动截屏，需要点击“开始识别”。

单屏使用时可点击“悬浮答案”：主窗口最小化，小答案窗保持置顶，可拖到题目区外（例如页面上方的状态栏处）。点击“展开主界面”返回。悬浮窗也提供开始 / 暂停按钮。

## 题库格式

支持有文字层的 PDF，例如用户指定的《2026 年度法治理论知识考试复习资料》格式：

```text
1、题干内容（）
A. 选项甲
B. 选项乙
C. 选项丙
D. 选项丁
正确答案：B
```

支持跨页题目、单选、多选、判断、分章节重复题号、多份题库合并、重复题目去重。相同题干与选项存在不同正确答案时，整次导入失败，保留原题库。缺答案、选项异常等题目会跳过并记录原因。

当前不对扫描 PDF 整本做 OCR；扫描件需要先转换为带文字层的 PDF。无题号、无选项、答案集中在独立答案表、复杂分栏和其他格式需要另行适配。

## 识别范围与更新

- 使用本机 RapidOCR 中文模型，截屏不上传云端；无需指定浏览器，不读取账号，不操作网页。
- 网页必须在屏幕上可见。窗口遮挡、浏览器最小化、屏幕锁定或题目被截断都会影响识别。程序发现自己的答案窗口遮挡区域时会清除答案并提示调整。
- 每个区域位于单块显示器内，支持在多显示器环境中选一块屏幕，按 Qt 的逻辑坐标抓取原始分辨率图像。显示器布局变化后需重选区域。
- 默认每 250 毫秒检查画面；画面稳定约 300 毫秒后在后台 OCR，实际更新速度取决于区域大小和 CPU。首次识别需要加载模型。请避开持续变化的计时器、光标及动画，否则画面可能一直无法稳定。
- 完整题干和全部选项内容匹配时，按网页顺序重新对应字母。只有选项不完整、题干能确定唯一答案时，才显示题库中的字母及正确选项全文，并标注“题库顺序”。全部选项已识别但内容与题库不一致时，提示核对，不回退成题库字母。相似题、缺字、未知题或答案歧义不显示答案。标点与排版空白统一处理，文字、否定词和数字保留。
- 只处理当前框内的一道题。可以只框选题干来获取题库答案；若需自动对应网页字母，请包含全部选项。长题可适当缩小浏览器比例后框选。
- 已按用户提供的考试卡片截图适配小圆框 / 方框中的独立 A/B/C/D 字母、题型标签及页内题号。建议只框选题目卡片，不包含上方考生资料、计时器和答题卡。

## 开发运行

需要 Python 3.11 或 3.12、Windows 10/11。双击 `安装依赖.cmd`，或在项目目录执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

打包后的整个 `dist\NewXKY` 文件夹可以复制到其他 Windows 电脑。请勿只复制 exe；`_internal` 中包含 Qt、OCR 模型和运行库。

本次本机验证中，最终 PyInstaller exe 被 Windows 应用程序控制策略拦截，因此本机另行准备了项目内的 Python 运行环境。此环境未提交到 Git 仓库。开发者可以在安装好依赖的 Windows Python 中执行 `python scripts/bundle_python.py` 生成 `runtime`，再连同 `newxky`、`main.py` 和启动脚本一起复制使用；无需依赖 Answering-S 目录或更改系统安全策略。

数据存放在程序旁的 `data\bank.json` 和 `data\settings.json`；源码运行时位于项目目录。请放在有写入权限的目录。`--data-dir` 可以指定其他存储目录。清空题库只清理缓存，不改动原 PDF。

主要模块：`bank.py` 解析和持久化，`matching.py` 内容核对和选项对应，`monitor.py` 画面版本及过期结果丢弃，`region.py` 框选，`ocr.py` 本地识别，`ui.py` 桌面界面和后台任务。

截图识别验证脚本接受自行提供的截图和题库缓存，例如：

```powershell
.\.venv\Scripts\python.exe scripts/verify_screenshots.py --bank data/bank.json --crop 60 410 1860 1253 --expect matched:B screenshot.png
```
