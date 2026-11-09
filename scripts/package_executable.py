"""Package the verified PyInstaller directory as a clean portable ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from newxky import __version__
from newxky.license_config import LICENSE_SERVER_URL
from newxky.default_bank import SOURCE_PDF_NAME
from newxky.runtime_manifest import missing_bank, missing_runtime

VERSION = __version__


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--allow-local", action="store_true",
                        help="allow a localhost test build; never use for distribution")
    args = parser.parse_args()
    if not args.allow_local:
        address = str(LICENSE_SERVER_URL or "")
        if not address.startswith("https://") or any(
            part in address.lower() for part in ("example.com", "localhost", "127.0.0.1")
        ):
            parser.error(
                "Set LICENSE_SERVER_URL in newxky/license_config.py to the public HTTPS "
                "license service before packaging (or use --allow-local for a test build)."
            )
    app = args.app_dir.resolve()
    output = (args.output or (ROOT / "dist" / f"NewXKY-V{VERSION}-Portable.zip")).resolve()
    dist = (ROOT / "dist").resolve()
    if not app.is_relative_to(dist) or not output.is_relative_to(dist):
        parser.error("Application and archive must be inside this project dist directory")
    if not (app / "NewXKY.exe").is_file() or not (app / "_internal").is_dir():
        parser.error("Build the standalone executable first")
    problems = missing_runtime(app / "_internal") + missing_bank(app)
    if problems:
        parser.error("构建目录缺少运行库文件，客户电脑上会提示 DLL 缺失：" + "、".join(problems))
    if not (ROOT / "题库" / "default-bank.json").is_file():
        parser.error("题库/default-bank.json is missing")
    try:
        manifest=json.loads((ROOT / '题库' / 'manifest.json').read_text(encoding='utf-8'))
        if (manifest['pdf']!=SOURCE_PDF_NAME
                or manifest['pdf_sha256']!=digest(ROOT/'题库'/SOURCE_PDF_NAME)
                or manifest['cache_sha256']!=digest(ROOT/'题库/default-bank.json')):
            parser.error('题库与指定 PDF 不一致，请重新执行 scripts/build.ps1')
    except (OSError,ValueError,KeyError,TypeError) as error:
        parser.error(f'指定 PDF 题库校验失败：{error}')
    if not args.allow_local:
        try:
            built = json.loads((app / "build-config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            parser.error(f"build-config.json missing or invalid: {error}")
        if built.get("license_server_url") != str(LICENSE_SERVER_URL or ""):
            parser.error("The built exe uses a different license address; rebuild before packaging")
        if built.get('version')!=VERSION or built.get('bank_sha256')!=manifest['cache_sha256']:
            parser.error('The built exe has an older version or question bank; rebuild before packaging')

    bundle = app / "题库"
    bundle.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "题库" / "default-bank.json", bundle / "default-bank.json")
    shutil.copy2(ROOT / "README.md", app / "使用说明.md")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", app / "THIRD_PARTY_NOTICES.md")
    checker = ROOT / "scripts" / "check_runtime.cmd"
    if not checker.is_file():
        parser.error("scripts/check_runtime.cmd is missing")
    shutil.copy2(checker, app / "运行环境检查.cmd")
    (app / "使用说明.txt").write_text(
        f"NewXKY 区域答题助手 V{VERSION} 免安装版\n\n"
        "1. 将整个 ZIP 解压到普通文件夹，双击 NewXKY.exe；不要只复制 exe。\n"
        "2. 首次启动输入软件验证码。每个验证码只能激活一台电脑，可用 40 分钟。\n"
        "3. 40 分钟内关闭软件后可以重新打开；到期后该验证码失效，需要新的验证码。\n"
        "4. 框住一道题的滚动区域，把答案窗口移到区域外，点击“开始识别”。\n"
        "5. 选项不全时自动滚动补全题干与选项，全部核对后显示当前页面的答案字母。\n"
        "6. 无法完全对应时，用红字标明题库顺序参考；请按选项内容核对。\n"
        "7. 滚动时会临时将鼠标移入框内；不点击选项或换题按钮。按 Esc 或暂停识别停止。\n\n"
        "如果双击 NewXKY.exe 没有反应、或提示缺少 DLL，请先双击同目录下的"
        "“运行环境检查.cmd”，它会指出缺少哪个文件。本程序需要 Windows 10 1809 或更新的"
        "64 位系统，并需要 Microsoft Visual C++ 2015-2022 运行库（x64）。\n\n"
        "截图和识别均在本机完成，不上传网络。保留 data 文件夹可恢复上次框选区域。\n",
        encoding="utf-8",
    )

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    sources = [ROOT / "main.py", *sorted((ROOT / "newxky").glob("*.py"))]
    metadata = {
        "format": "PyInstaller onedir",
        "product": "NewXKY",
        "version": VERSION,
        "platform": "Windows x64",
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "source_revision": revision,
        "source_modified": bool(status.strip()),
        "python": platform.python_version(),
        "license_server_url": str(LICENSE_SERVER_URL or ""),
        "exe_sha256": digest(app / "NewXKY.exe"),
        "bank_sha256": digest(bundle / "default-bank.json"),
        "source_pdf": manifest,
        "source_sha256": {
            str(path.relative_to(ROOT)).replace("\\", "/"): digest(path) for path in sources
        },
    }
    (app / "build-info.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    files = [
        app / "NewXKY.exe",
        *(
            path for path in (app / "_internal").rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        ),
        *(
            app / name for name in (
                "使用说明.md", "使用说明.txt", "THIRD_PARTY_NOTICES.md",
                "build-info.json", "build-config.json", "运行环境检查.cmd",
            )
        ),
        app / "题库" / "default-bank.json",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + "." + uuid4().hex + ".partial")
    try:
        import zipfile
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(files):
                archive.write(path, (Path("NewXKY") / path.relative_to(app)).as_posix())
        print("ZIP_CREATED_CHECKING", len(files), flush=True)
        with zipfile.ZipFile(temporary) as archive:
            assert archive.testzip() is None
            assert all(
                Path(name).parts[1] not in {"data", "人员记录", "人员结果", "license.dat"}
                for name in archive.namelist()
            )
            assert "NewXKY/NewXKY.exe" in archive.namelist()
            assert "NewXKY/题库/default-bank.json" in archive.namelist()
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    checksum = digest(output)
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{checksum}  {output.name}\n", encoding="utf-8"
    )
    print("PORTABLE_READY", str(output), output.stat().st_size, checksum, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
