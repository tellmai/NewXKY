# NewXKY 区域答题助手 V3.0.1

Windows 本地桌面程序。框选屏幕中的一道题，程序用本机 OCR 识别题干和选项，在内置题库中匹配正确答案。选项显示不全时自动在框内滚动，读完后按当前页面的字母显示答案；无法完全核对时用红字显示题库顺序参考。

当前正式授权服务：`https://license.newxky-license.com`  
正式免安装包：`dist\NewXKY-V3.0.1-Portable.zip`

## 功能

- 内置题库（随安装包提供，界面只显示题库数量、题型和来源）。
- 框选屏幕区域后持续识别；题目文字变化后自动更新。
- 自动滚动补全：支持网页和桌面小程序中的题目区域；从中间开始时先向上读取题干，再向下收集全部选项。按 Esc 或暂停识别可停止。
- 关键词搜题（Ctrl+F）：按题干或选项关键词搜索 2026知识库，查看完整题目和答案。
- 答案区优先显示实际页面的正确字母及选项内容。滚动读取期间不提前显示题库字母；无法补全时明确标红“题库顺序”。
- 未完全匹配时按题干/选项关键词检索最相近的题目，以红色“相似题参考”显示参考答案并提示核对。
- 顶部授权状态：`已验证 · 剩余 MM:SS`。
- 无 PDF 导入、清空题库、人员管理、浏览器选择、自动答题、悬浮窗等旧功能。

## 授权规则

1. 首次启动输入 16 位验证码（格式 `XXXX-XXXX-XXXX-XXXX`）。
2. 每个验证码只能绑定一台电脑；激活后从首次输入时起算 **40 分钟**。
3. 同一台电脑在这 40 分钟内可以关闭并重新打开软件；到期后该验证码永久失效，需要新的验证码。
4. 把安装包或本机授权记录复制到另一台电脑，验证码和服务端都会拒绝；客户端本地记录还使用 Windows DPAPI 加密并按机器指纹校验。
5. 换电脑、重装系统或更换系统盘后，原验证码不能再次使用。

V3.0.1 使用服务端 Ed25519 签名校验机器绑定和最长 40 分钟租约，拒绝篡改的有效期、时间偏移与未认证缓存。Windows 加密失败不会退回明文保存。旧 DPAPI 缓存首次升级需要联网确认，原到期时间不延长；请保持 Windows 时间与服务器一致，相差超过 5 分钟时先校准系统时间。

授权由联网服务端判定，纯离线程序无法做到“验证码只能用一次、换机失效”。服务端部署见 [`license_server/README.md`](license_server/README.md)；从购买服务器/域名到 HTTPS 验证的逐步操作见 [`部署操作清单.md`](部署操作清单.md)。

## 题库来源与更新

当前内置题库来自 `题库\2026年度知识考试复习资料.pdf`，构建时解析为 `题库\default-bank.json`：

```powershell
.\.venv\Scripts\python.exe scripts\build_bank_from_pdf.py
```

- 当前：349 页、1,291 道有效题、0 条解析异常，来源统一显示为 **2026知识库**。
- 运行时只读取 JSON，不加载 PDF，因此安装包不需要 pdfplumber/pdfminer，也不会出现 PDF 导入界面。
- 更新题库后重新运行上面的命令，再按本文档重新构建 exe/ZIP。
- 题目内容如需修订，必须先修改 Git 跟踪的源 PDF，再生成 JSON 与 manifest 并一并提交，不能只改缓存。当前 844 的 A/C、845 的 B/D 在源 PDF 中本就相同，本版按原文保留并正确计数匹配。
- 如果 PDF 中新增题目，直接替换 `题库\2026年度知识考试复习资料.pdf` 后重新生成即可；解析异常会写入 `题库\manifest.json` 的 issues 数量并在构建输出中列出。

## 使用

1. 安装包完整解压后双击 `NewXKY.exe`。不要只复制 exe，`_internal` 和 `题库` 文件夹必须保留。

   runtime 免安装包使用 `runtime` 文件夹替代 `_internal`；请完整保留包内所有文件，运行时和 VC++ DLL 已随包提供。
2. 输入分发的验证码，点击“激活软件”。
3. 打开浏览器或小程序答题页，点击“框选 / 重选区域”，框住**一道题的内容滚动区域**；尽量包含题干和选项，可包含右侧滚动条。Esc 或右键取消。
4. 把答案窗口移到框选区域外，点击“开始识别”。
5. 默认勾选“选项不全时自动滚动”。题干或选项不全时会滚动补全，核对全部选项后按页面顺序给答案。滚动会临时将鼠标移入框内并激活该考试窗口；不点击答案或换题按钮，鼠标未被用户移动时自动归位。按 Esc 或“暂停识别”可停止。
6. 如果答案区显示“未精确匹配”，可点击顶部“关键词搜题”（Ctrl+F）输入题干关键词，查看 2026知识库 中的完整题目和答案。
7. 到期后主界面显示“授权已到期”，点击“输入新验证码”可以继续使用新的验证码。

> 授权状态显示“离线续用”表示暂时连不上授权服务器，程序会按本机记录继续倒计时；到期后同样会锁定。重新联网后会自动恢复“已验证”。

## 运行环境与启动报错

要求 **Windows 10 1809 或更新的 64 位系统**（Windows 11 同样可用）。程序自带 Python 与 Qt，不需要另装 Python，但建议安装 **Microsoft Visual C++ 2015-2022 运行库（x64）**。

解压后的目录里必须有 `NewXKY.exe`、`_internal` 文件夹、`题库` 文件夹；三者缺一都会启动失败。**不要只复制 exe，也不要在压缩包里直接双击**。

双击没有反应或提示缺少 DLL 时，先双击同目录下的 `运行环境检查.cmd`，它会逐项列出 `_internal` 里缺了哪个文件。常见提示对应关系：

| 提示 | 原因 | 处理 |
|---|---|---|
| `无法启动此程序，因为计算机中丢失 api-ms-win-core-sysinfo-l1-2-0.dll` | 系统低于 Windows 10，或系统文件被精简版/优化工具删除；此时 Python 本身无法启动 | 换用 Windows 10 1809+ 的 64 位系统；此类机器上程序无法运行 |
| `Failed to execute script 'main' ... DLL load failed while importing QtCore` | `_internal\PySide6` 缺失或被安全软件删除；也可能是没装 VC++ 运行库 | 重新完整解压；把程序加入安全软件白名单；安装 VC++ 2015-2022 运行库 x64 |
| 双击后闪一下就退出，`data\startup-error.log` 有记录 | 缺少文件或被拦截 | 同上，并用 `运行环境检查.cmd` 核对 |
| 提示“程序文件不完整，缺少以下组件” | 程序自检发现安装不完整 | 按弹窗里的列表重新解压或补装运行库 |

正式包由 `scripts/release.ps1` 构建；构建与打包阶段都会按 `newxky/runtime_manifest.py` 里的清单校验运行库，缺文件时直接失败，不会生成有问题的 ZIP。

## 软件说明

主界面“软件说明”按钮显示当前版本、授权状态和剩余时间：

- 版本：V3.0.1
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

## 构建 V3.0.1 免安装包

拿到公网 HTTPS 地址后，可以一步完成“写入地址 → 构建 → 免安装 ZIP → 服务端部署 ZIP”：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\release.ps1 -LicenseServer https://license.你的域名.com
```

也可以分步执行：

先生成或复用授权签名密钥：

```powershell
.\runtime\python.exe scripts\configure_license_signing.py
```

私钥保存在被 Git 忽略的 `license_server/data/lease-signing-key.pem`，公钥写入客户端配置；后续发版复用并备份同一私钥。先部署配套授权服务端，再分发新客户端。

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
dist\NewXKY-V3.0.1-Portable.zip
dist\NewXKY-V3.0.1-Portable.zip.sha256
```

包内只包含程序、运行库、OCR 模型和 `题库/default-bank.json`，不包含 PDF、人员资料、授权码或本机 `data`。

### 没有 PyInstaller 时的等价出包方式

发布机如果装不了 PyInstaller（没有 pip、不能联网），可以用随包的 `runtime` 运行时出同样的免安装包：

```powershell
.\runtime\python.exe scripts\package_runtime.py
```

它会把程序源码、`题库`、`assets` 和 `runtime` 组装到 `dist\release-runtime-<时间戳>\NewXKY`，用 Windows 自带的 C# 编译器（`csc.exe`）编译一个 `NewXKY.exe` 启动器（源码见 `scripts/launcher.cs`），再打成 `dist\NewXKY-V3.0.1-Portable.zip`。用户侧体验与 PyInstaller 版一致：解压后双击 `NewXKY.exe`。

- 默认会剔除客户端用不到的包（playwright、ddddocr、pdfplumber、openpyxl 等），加 `--keep-runtime` 可保留完整运行时。
- 打包前会校验 `题库/default-bank.json` 与 `manifest.json`、源 PDF 的哈希，并在打包后实际导入 PySide6/OCR 依赖做一次自检，不通过不会生成 ZIP。
- 这个包依赖 .NET Framework 4.x（Windows 10 1809+ 自带）来启动 `NewXKY.exe`。

同时可以生成授权服务端部署包（含已播种的 `licenses.db`，不含明文验证码）：

```powershell
.\.venv\Scripts\python.exe scripts\package_server.py
```

输出 `dist\NewXKY-LicenseServer-V3.0.1.zip`，上传服务器后按 [`license_server/README.md`](license_server/README.md) 配置 systemd 和 Caddy。

### 精简 runtime 免安装包

构建机已有 `runtime` 时，可直接生成自带 Python、Qt、OCR 模型和 VC++ DLL 的免安装 ZIP：

```powershell
.\runtime\python.exe scripts\package_runtime.py
```

默认剔除浏览器自动化、PDF/Excel 工具、未使用的 Qt 模块、FFmpeg 和字节码缓存，保留截图、自动滚动、OCR、授权签名校验所需组件。生成的 ZIP 可直接在 Windows 10 1809+ / Windows 11 的 64 位电脑上完整解压运行，无需另装 Python。

`--reuse --dist-root ...` 只允许复用源码、题库和当前分支完全一致的目录；旧版本、不同题库或残留旧模块会被拒绝，避免把旧程序重新标成新版本。

只升级已有授权服务器、无需初始验证码数据库时：

```powershell
.\runtime\python.exe scripts\package_server.py --upgrade-only --output dist\NewXKY-LicenseServer-V3.0.1-Update.zip
```

更新包保留现网激活记录，包含服务端签名私钥，只用于服务器维护，不能交给客户端用户。

> 正式包必须填入公网 HTTPS 地址后重新构建；未配置地址时打包脚本会拒绝生成正式 ZIP。

### Windows 功能测试包（无需公网服务器）

如果没有公网授权地址，可以使用：

```text
dist\NewXKY-V3.0.1-WindowsTest.zip
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
  runtime_manifest.py      打包运行库清单（启动自检、构建与打包校验共用）
  matching.py              题干/选项匹配、模糊检索
  keyword_search.py        关键词搜题窗口
  selfcheck.py             隐藏的 OCR/题库自检入口
  ocr.py / ocr_engine.py   本地 OCR
  monitor.py               画面稳定检测
  region.py                框选区域
  scroll_scan.py           跨屏题干/选项拼接
  region_scroll.py         框内滚轮输入
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
  package_executable.py    免安装 ZIP 打包（PyInstaller 产物）
  package_runtime.py       免安装 ZIP 打包（随包 runtime + 启动器，无需 PyInstaller）
  launcher.cs              runtime 版 NewXKY.exe 启动器源码
  package_test_bundle.py   带本机授权服务的功能测试包
  package_server.py        授权服务端部署 ZIP
  check_runtime.cmd        客户机上的运行环境检查（随包分发为“运行环境检查.cmd”）
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

### 滚动识别与题库校验

- 只有实际读到的题干、选项能参与拼接，不从题库补造画面中缺失的字。跨屏有文字冲突时不会显示“已核对”答案。
- 每题最多 28 次滚动；连续两次没有新内容则停止。读不到完整内容或系统拒绝滚动时，按红字“题库顺序”提供参考，可重新框选、手动滚动或用关键词搜题。
- “请选择一个答案”“请选择所有正确选项”等整行界面提示不会混入题干；单个选项恰好也是题库中的判断题题干时，不再误认为框入多道题。
- `scripts/build.ps1` 每次构建都会从项目 `题库/2026年度知识考试复习资料.pdf` 重新生成缓存。打包时校验 PDF、缓存和 EXE 构建记录的哈希与版本，避免使用旧题库。

## 依赖

运行依赖：PySide6-Essentials、RapidOCR（ONNX Runtime 模型）、OpenCV、NumPy、Pillow、cryptography。授权服务端使用 Python 标准库和 cryptography 签发租约；生成 Excel 需要 openpyxl（仅开发/分发工具）。第三方许可见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
