"""Bundle the existing Python runtime and installed runtime dependencies locally.

No downloads, package installation or system configuration changes are made.
Run with a working Windows Python containing requirements.txt.
"""
import shutil
import sys
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / "runtime"
    if destination.resolve().parent != root:
        raise ValueError("Runtime destination must remain in this project")
    destination.mkdir(exist_ok=True)
    base = Path(sys.base_prefix)
    for name in ("python.exe", "pythonw.exe", "python3.dll", "python311.dll", "python312.dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        source = base / name
        if source.is_file():
            shutil.copy2(source, destination / name)
    for name in ("Lib", "DLLs"):
        shutil.copytree(base / name, destination / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("site-packages", "__pycache__", "test", "tests"))
    packages = destination / "Lib/site-packages"
    packages.mkdir(exist_ok=True)
    todo = ["PySide6-Essentials", "pdfplumber", "rapidocr-onnxruntime", "Pillow"]
    seen = set()
    versions = []
    while todo:
        name = canonicalize_name(todo.pop())
        if name in seen:
            continue
        seen.add(name)
        dist = distribution(name)
        for dependency in dist.requires or []:
            requirement = Requirement(dependency)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                todo.append(requirement.name)
        for entry in dist.files or []:
            # Distribution entry points may reference ../../../Scripts. Only
            # package files inside site-packages are copied into this bundle.
            if entry.is_absolute() or ".." in entry.parts:
                continue
            if "__pycache__" in entry.parts or str(entry).endswith(".pyc"):
                continue
            source = Path(dist.locate_file(entry))
            if source.is_file():
                target = packages / entry
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        versions.append(f"{dist.metadata['Name']}=={dist.version}")
        print(versions[-1], flush=True)
    (destination / "requirements-bundled.txt").write_text("\n".join(sorted(versions)) + "\n", encoding="utf-8")
    print("LOCAL_PYTHON_READY", destination, flush=True)


if __name__ == "__main__":
    main()
