"""Build a portable ZIP with an unmodified, signed official Python runtime.

Only project-local files are written. No system installation or security
setting changes are made. Dependencies are installed from official PyPI wheels.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = "3.14.10"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_SHA256 = "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"
PIP_URL = "https://files.pythonhosted.org/packages/07/25/ee8c38ae72d66b844ce8eb9711ba905dba21ca1a8a0c960057c41cd23337/pip-26.3-py3-none-any.whl"
PIP_SHA256 = "f3b60b20ffaadd4415ed7957212a38ac63fa4c5fa375bd0f4a797777940fad13"


def download(url, path, expected):
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        print(f"Downloading {path.name}", flush=True)
        temporary = path.with_suffix(".download")
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as file:
            shutil.copyfileobj(response, file)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
            raise ValueError(f"SHA-256 mismatch for {path.name}")
        temporary.replace(path)
    return path


def extract(archive, destination):
    with zipfile.ZipFile(archive) as file:
        for entry in file.infolist():
            if not (destination / entry.filename).resolve().is_relative_to(destination.resolve()):
                raise ValueError("Archive contains an unsafe path")
        file.extractall(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/NewXKY-portable")
    parser.add_argument("--skip-install", action="store_true", help="Reuse dependencies already present in the output")
    parser.add_argument("--models-dir", type=Path, help="Use an existing PP-OCRv4 model directory")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Build on Windows x64")
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "dist").resolve()):
        parser.error("Output must be inside this project's dist directory")
    output.mkdir(parents=True, exist_ok=True)
    cache = ROOT / "tmp/portable-build"
    cache.mkdir(parents=True, exist_ok=True)
    python_zip = download(PYTHON_URL, cache / f"python-{PYTHON_VERSION}-embed-amd64.zip", PYTHON_SHA256)
    runtime = output / "runtime"
    runtime.mkdir(exist_ok=True)
    extract(python_zip, runtime)
    query = "$ErrorActionPreference='Stop'; @('python.exe','pythonw.exe','python314.dll') | ForEach-Object { $s = Get-AuthenticodeSignature -LiteralPath (Join-Path $env:NEWXKY_SIGN_ROOT $_); [PSCustomObject]@{file=$_;status=$s.Status.ToString();signer=$s.SignerCertificate.Subject} } | ConvertTo-Json -Compress"
    check = subprocess.run([shutil.which("pwsh") or "powershell", "-NoProfile", "-NonInteractive", "-Command", query],
                           env=dict(os.environ, NEWXKY_SIGN_ROOT=str(runtime)), capture_output=True, text=True, check=True)
    signatures = json.loads(check.stdout)
    if any(item["status"] != "Valid" or "Python Software Foundation" not in item["signer"] for item in signatures):
        raise ValueError("Official Python runtime signature verification failed")
    print("Official Python signatures: VALID", flush=True)
    (runtime / "python314._pth").write_text("python314.zip\n.\nLib/site-packages\n..\nimport site\n", encoding="utf-8")
    if not args.skip_install:
        pip_wheel = download(PIP_URL, cache / "pip-26.3-py3-none-any.whl", PIP_SHA256)
        pip_root = cache / "pip"
        extract(pip_wheel, pip_root)
        runner = cache / "run_pip.py"
        runner.write_text("import sys, runpy\nsys.path.insert(0, " + repr(str(pip_root)) + ")\nrunpy.run_module('pip', run_name='__main__')\n", encoding="utf-8")
        subprocess.run([str(runtime / "python.exe"), str(runner), "install", "--only-binary=:all:", "--no-compile",
                        "--disable-pip-version-check", "--index-url", "https://pypi.org/simple",
                        "--cache-dir", str(cache / "pip-cache"), "--target", str(runtime / "Lib/site-packages"),
                        "--report", str(output / "build-install.json"), "-r", str(ROOT / "requirements-portable.txt")], check=True)
    # Reuse the previously verified PP-OCRv4 models from the upstream wheel.
    # The old Python package itself is not installed in the modern runtime.
    model_dir = output / "assets/ocr"
    model_dir.mkdir(parents=True, exist_ok=True)
    existing_models = args.models_dir
    legacy = importlib.util.find_spec("rapidocr_onnxruntime")
    if existing_models is None and legacy is not None:
        existing_models = Path(legacy.origin).parent / "models"
    if existing_models is not None:
        for name in ("ch_PP-OCRv4_det_infer.onnx", "ch_PP-OCRv4_rec_infer.onnx", "ch_ppocr_mobile_v2.0_cls_infer.onnx"):
            shutil.copy2(existing_models / name, model_dir / name)
        from importlib.metadata import distribution
        if legacy is not None:
            dist = distribution("rapidocr-onnxruntime")
            for entry in dist.files or []:
                if ".dist-info/" in str(entry).replace('\\', '/') and "license" in str(entry).lower():
                    shutil.copy2(dist.locate_file(entry), model_dir / "LICENSE")
    else:
        model_wheels = list(cache.glob("rapidocr_onnxruntime-1.4.4-*.whl"))
        if not model_wheels:
            subprocess.run([str(runtime / "python.exe"), str(cache / "run_pip.py"), "download",
                            "--only-binary=:all:", "--no-deps", "--python-version", "3.12",
                            "--disable-pip-version-check", "--index-url", "https://pypi.org/simple",
                            "--dest", str(cache), "rapidocr-onnxruntime==1.4.4"], check=True)
            model_wheels = list(cache.glob("rapidocr_onnxruntime-1.4.4-*.whl"))
        with zipfile.ZipFile(model_wheels[0]) as file:
            for entry in file.namelist():
                if entry.startswith("rapidocr_onnxruntime/models/") and entry.endswith(".onnx"):
                    (model_dir / Path(entry).name).write_bytes(file.read(entry))
                elif ".dist-info/" in entry and "license" in entry.lower():
                    (model_dir / "LICENSE").write_bytes(file.read(entry))
    for name in ("main.py", "portable_start.py", "requirements-portable.txt", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, output / name)
    shutil.copytree(ROOT / "newxky", output / "newxky", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    launcher = '@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\nstart "NewXKY" "runtime\\pythonw.exe" "portable_start.py"\r\n'
    (output / "启动软件.cmd").write_bytes(launcher.encode("utf-8"))
    diagnostic = '@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\n"runtime\\python.exe" "main.py"\r\npause\r\n'
    (output / "启动并查看错误.cmd").write_bytes(diagnostic.encode("utf-8"))
    (output / "使用说明.txt").write_text(
        "NewXKY 免安装便携版\n\n1. 将整个 ZIP 解压到普通文件夹。\n2. 双击“启动软件.cmd”。不要在 ZIP 内直接运行。\n"
        "3. 导入 PDF，框选题目区域，再开始识别。\n4. 看得全时按网页选项顺序显示；看不全时按题库顺序显示并标明。\n\n"
        "本包内含 Python、Qt、OCR 模型和依赖，无需另外安装 Python 或联网下载模型。\n"
        "程序数据保存在 data 文件夹。请保留 runtime 和 newxky 文件夹。\n"
        "此版本使用 Python 官方签名的运行程序，不包含原 PyInstaller NewXKY.exe。\n"
        "Windows 的应用信任判定仍以系统实际策略为准。若有拦截，请记录被拦截文件名，勿关闭系统安全功能。\n",
        encoding="utf-8")
    metadata = {"python_version": PYTHON_VERSION, "python_source": PYTHON_URL, "python_sha256": PYTHON_SHA256,
                "model_sha256": {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in model_dir.glob("*.onnx")},
                "runtime_signatures": signatures, "format": "portable-python", "platform": "Windows x64"}
    (output / "build-info.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(ROOT / "验证记录.md", output / "验证记录.md")
    archive = output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as file:
        for path in sorted(output.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.relative_to(output).parts[0] != "data":
                file.write(path, str(Path(output.name) / path.relative_to(output)))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print("PORTABLE_READY", archive, digest, flush=True)


if __name__ == "__main__":
    main()
