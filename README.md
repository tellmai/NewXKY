# NewXKY 区域答题助手 V1.0.0

Windows 本地桌面程序。框选屏幕中的一道题，程序用本机 OCR 识别题干和选项，在内置题库中匹配正确答案。**不自动答题、不连接浏览器、不操作鼠标、不导入 PDF。**

当前正式授权服务：`https://license.newxky-license.com`  
正式免安装包：`dist\NewXKY-V1.0.0-Portable.zip`

## 功能

- 内置题库（随安装包提供，界面只显示题库数量、题型和来源）。
- 框选屏幕区域后持续识别；题目文字变化后自动更新。
- 关键词搜题（Ctrl+F）：按题干或选项关键词搜索 2026知识库，查看完整题目和答案。
- 答案区显示正确字母、完整选项、题库来源，并区分“网页选项已核对”“题库顺序参考”“相似题参考”等情况。
- 未完全匹配时按题干/选项关键词检索最相近的题目，以红色“相似题参考”显示参考答案并提示核对。
- 顶部授权状态：`已验证 · 剩余 MM:SS`。
- 无 PDF 导入、清空题库、人员管理、浏览器选择、自动答题、悬浮窗等旧功能。

## 授权规则

1. 首次启动输入 16 位验证码（格式 `XXXX-XXXX-XXXX-XXXX`）。
2. 每个验证码只能绑定一台电脑；激活后从首次输入时起算 **40 分钟**。
3. 同一台电脑在这 40 分钟内可以关闭并重新打开软件；到期后该验证码永久失效，需要新的验证码。
4. 把安装包或本机授权记录复制到另一台电脑，验证码和服务端都会拒绝；客户端本地记录还使用 Windows DPAPI 加密并按机器指纹校验。
5. 换电脑、重装系统或更换系统盘后，原验证码不能再次使用。

授权由联网服务端判定，纯离线程序无法做到“验证码只能用一次、换机失效”。服务端部署见 [`license_server/README.md`](license_server/README.md)；从购买服务器/域名到 HTTPS 验证的逐步操作见 [`部署操作清单.md`](部署操作清单.md)。

## 题库来源与更新

当前内置题库来自 `题库\2026考试复习资料.pdf`，构建时解析为 `题库\default-bank.json`：

```powershell
.\.venv\Scripts\python.exe scripts\build_bank_from_pdf.py
```

- 当前：349 页、1,288 道有效题，来源统一显示为 **2026知识库**。
- 运行时只读取 JSON，不加载 PDF，因此安装包不需要 pdfplumber/pdfminer，也不会出现 PDF 导入界面。
- 更新题库后重新运行上面的命令，再按本文档重新构建 exe/ZIP。
- 如果 PDF 中新增题目，直接替换 `题库\2026考试复习资料.pdf` 后重新生成即可；解析异常会写入 `题库\manifest.json` 的 issues 数量并在构建输出中列出。

## 使用

1. 安装包完整解压后双击 `NewXKY.exe`。不要只复制 exe，`_internal` 和 `题库` 文件夹必须保留。
2. 输入分发的验证码，点击“激活软件”。
3. 打开浏览器答题页，点击主界面“框选 / 重选区域”，拖动框住**一道题的完整题干和全部选项**。Esc 或右键取消。
4. 把答案窗口移到框选区域外，点击“开始识别”。
5. 题目变化后自动重新识别；点击“暂停识别”可停止截图和 OCR。
6. 如果答案区显示“未精确匹配”，可点击顶部“关键词搜题”（Ctrl+F）输入题干关键词，查看 2026知识库 中的完整题目和答案。
7. 到期后主界面显示“授权已到期”，点击“输入新验证码”可以继续使用新的验证码。

> 授权状态显示“离线续用”表示暂时连不上授权服务器，程序会按本机记录继续倒计时；到期后同样会锁定。重新联网后会自动恢复“已验证”。

## 软件说明

主界面“软件说明”按钮显示当前版本、授权状态和剩余时间：

- 版本：V1.0.0
- 状态：已验证 / 离线续用 / 授权已到期
- 剩余时间：40 分钟倒计时
- 隐私：截图、OCR 和题库匹配均在本机完成，不上传网络。

## 开发运行

需要 Windows 10/11、Python 3.11 或 3.12。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m pytest -q
```

开发时可以在源码环境中用环境变量连接本地授权服务（打包后的 exe 忽略该变量，只使用编译进程序的地址）：

```powershell
$env:NEWXKY_LICENSE_SERVER = 'http://127.0.0.1:8787'
.\.venv\Scripts\python.exe main.py
```

## 构建 V1.0.0 免安装包

拿到公网 HTTPS 地址后，可以一步完成“写入地址 → 构建 → 免安装 ZIP → 服务端部署 ZIP”：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\release.ps1 -LicenseServer https://license.你的域名.com
```

也可以分步执行：

1. 先在 `newxky/license_config.py` 填入公网 HTTPS 授权地址：

   ```powershell
   .\.venv\Scripts\python.exe scripts\set_license_url.py https://license.你的域名.com
   ```

   也可以直接编辑文件：

   ```python
   LICENSE_SERVER_URL = "https://license.example.com"
   ```

2. 构建 PyInstaller 目录：

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\build.ps1
   ```

   重复构建时如果旧的 `dist\release\NewXKY` 正被系统占用，可指定独立目录：

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -DistRoot dist\release-20261108
   ```

3. 生成免安装 ZIP：

   ```powershell
   .\.venv\Scripts\python.exe scripts\package_executable.py --app-dir dist\release\NewXKY
   ```

输出：

```text
dist\NewXKY-V1.0.0-Portable.zip
dist\NewXKY-V1.0.0-Portable.zip.sha256
```

包内只包含程序、运行库、OCR 模型和 `题库/default-bank.json`，不包含 PDF、人员资料、授权码或本机 `data`。

同时可以生成授权服务端部署包（含已播种的 `licenses.db`，不含明文验证码）：

```powershell
.\.venv\Scripts\python.exe scripts\package_server.py
```

输出 `dist\NewXKY-LicenseServer-V1.0.0.zip`，上传服务器后按 [`license_server/README.md`](license_server/README.md) 配置 systemd 和 Caddy。

> 正式包必须填入公网 HTTPS 地址后重新构建；未配置地址时打包脚本会拒绝生成正式 ZIP。

### Windows 功能测试包（无需公网服务器）

如果没有公网授权地址，可以使用：

```text
dist\NewXKY-V1.0.0-WindowsTest.zip
```

解压后双击 `启动测试版.cmd`，它会先启动随包的 `NewXKY-TestLicenseServer.exe`，再启动软件。验证码在 `test-license\测试验证码.txt`，共 5 个，每个只能激活一台电脑、可用 40 分钟。此包仅用于功能验收，不能作为正式分发包；正式分发必须使用公网 HTTPS 授权服务。

## 验证码文件

生成 20 个 Excel，每份 500 个，共 10,000 个：

```powershell
.\.venv\Scripts\python.exe license_server\generate_codes.py --count 10000 --files 20 --per-file 500
```

输出到 `dist\授权码-40分钟\NewXKY授权码-01.xlsx` 到 `-20.xlsx`，同时把验证码哈希写入 `license_server\data\licenses.db`。明文验证码只存在于 Excel 中；服务端数据库只保存 SHA-256。

如果已有 Excel，也可以导入：

```powershell
.\.venv\Scripts\python.exe license_server\import_codes.py dist\授权码-40分钟\*.xlsx --db license_server\data\licenses.db
```

## 目录

```text
main.py                    程序入口
newxky/
  ui.py                    简洁主界面、倒计时
  licensing.py             激活客户端、机器绑定、40 分钟租约
  license_config.py        发版时填入的 HTTPS 授权地址
  bank.py                  题库 JSON 读写
  default_bank.py          加载内置题库
  matching.py              题干/选项匹配、模糊检索
  keyword_search.py        关键词搜题窗口
  selfcheck.py             隐藏的 OCR/题库自检入口
  ocr.py / ocr_engine.py   本地 OCR
  monitor.py               画面稳定检测
  region.py                框选区域
license_server/
  server.py                标准库 HTTPS 反向代理后的授权服务
  db.py                    SQLite 单次激活逻辑
  generate_codes.py        生成 10,000 个验证码和 Excel
  import_codes.py          导入已有 Excel
  data/licenses.db         验证码哈希与激活记录
scripts/
  build.ps1                PyInstaller 构建
  build_bank_from_pdf.py   从复习资料 PDF 生成内置题库
  release.ps1              一键正式构建与打包
  package_executable.py    免安装 ZIP 打包
  package_test_bundle.py   带本机授权服务的功能测试包
  package_server.py        授权服务端部署 ZIP
  set_license_url.py       写入正式授权服务地址
  test_server_entry.py     功能测试包授权服务入口
  generate_icon.py         图标生成
```

## 数据与隐私

- `data/settings.json`：上次框选区域。
- `data/license.dat`：DPAPI 加密的本机授权记录（机器指纹、到期时间）。
- `题库/default-bank.json`：内置题库，只读使用。
- 截图和 OCR 结果不会上传；只有激活/续期时向授权服务器发送验证码、机器指纹和版本号。
- 更新软件时保留 `data` 文件夹可保留上次框选区域；授权到期后旧验证码不会因保留文件而复活。

## 依赖

运行依赖：PySide6-Essentials、RapidOCR（ONNX Runtime 模型）、OpenCV、NumPy、Pillow。授权服务端只用 Python 标准库；生成 Excel 需要 openpyxl（仅开发/分发工具）。第三方许可见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
