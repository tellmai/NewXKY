"""Prepare and restore the PDF shipped beside the executable."""
import hashlib
import json
import shutil
from pathlib import Path

from .bank import load_pdf,merge_banks,read_bank,save_bank

BUNDLE_DIRECTORY="题库"
DEFAULT_PDF_NAME="2026 年度法治理论知识考试.pdf"
CACHE_NAME="default-bank.json"
MANIFEST_NAME="manifest.json"


def file_digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def _manifest(directory):
    data=json.loads((directory/MANIFEST_NAME).read_text(encoding="utf-8"))
    if not isinstance(data,dict):
        raise ValueError("随包题库清单无效")
    name=data.get("pdf","")
    if data.get("version")!=1 or not isinstance(name,str) or Path(name).name!=name or Path(name).suffix.lower()!=".pdf":
        raise ValueError("随包题库清单无效")
    return data


def _cached_bundle(directory,manifest):
    if (file_digest(directory/manifest["pdf"])!=manifest["pdf_sha256"]
            or file_digest(directory/CACHE_NAME)!=manifest["cache_sha256"]):
        raise ValueError("随包题库缓存与 PDF 不一致")
    bank=read_bank(directory/CACHE_NAME)
    if not bank.questions:
        raise ValueError("随包题库缓存为空")
    return bank


def prepare_bundle(pdf_path,directory):
    """Copy the original PDF byte-for-byte and cache its verified extraction."""
    source=Path(pdf_path).resolve()
    directory=Path(directory)
    if source.suffix.lower()!=".pdf" or not source.is_file():
        raise ValueError("请选择有效的默认 PDF 题库")
    before=file_digest(source)
    try:
        manifest=_manifest(source.parent)
        if manifest["pdf"]!=source.name:
            raise ValueError("缓存对应其他 PDF")
        bank=_cached_bundle(source.parent,manifest)
    except (OSError,ValueError,KeyError,TypeError):
        bank=merge_banks([load_pdf(source)])
    if not bank.questions:
        raise ValueError("默认 PDF 未解析出有效题目")
    if file_digest(source)!=before:
        raise ValueError("PDF 在打包过程中发生变化，请重新打包")
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/source.name
    if target.resolve()!=source:
        shutil.copy2(source,target)
    if file_digest(target)!=before:
        raise ValueError("随包 PDF 复制校验失败")
    bank.sources=[source.name]
    save_bank(bank,directory/CACHE_NAME)
    manifest={"version":1,"pdf":source.name,"pdf_sha256":before,
              "cache_sha256":file_digest(directory/CACHE_NAME),"questions":len(bank.questions),
              "pages":bank.page_count,"issues":len(bank.issues)}
    temporary=directory/(MANIFEST_NAME+".tmp")
    temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(directory/MANIFEST_NAME)
    return manifest


def load_bundled_bank(app_dir):
    directory=Path(app_dir)/BUNDLE_DIRECTORY
    try:
        manifest=_manifest(directory)
    except (OSError,ValueError,TypeError):
        manifest=None
    pdf=directory/(manifest["pdf"] if manifest else DEFAULT_PDF_NAME)
    if not pdf.is_file():
        return None,[]
    try:
        bank=_cached_bundle(directory,manifest) if manifest else None
    except (OSError,ValueError,KeyError,TypeError):
        bank=None
    if bank is None:
        bank=merge_banks([load_pdf(pdf)])
    notes=[f"随包题库已加载：{len(bank.questions)} 题 · 异常 {len(bank.issues)} 条",f"随包 PDF：{pdf.name}",*bank.issues]
    return bank,notes


def restore_startup_bank(data_dir,app_dir):
    """Merge defaults with local imports without replacing conflicting data."""
    try:
        bundled,notes=load_bundled_bank(app_dir)
    except Exception as error:
        bundled,notes=None,[f"随包 PDF 读取失败：{error}"]
    cache=Path(data_dir)/"bank.json"
    try:
        existing=read_bank(cache)
    except (OSError,ValueError,TypeError,KeyError):
        if bundled is None:
            raise
        return bundled,[*notes,"本地题库缓存无法读取，已使用随包题库；原缓存文件保留。"]
    if bundled is None:
        return existing,notes
    try:
        merged=merge_banks([existing,bundled])
    except ValueError as error:
        return existing,[f"随包题库存在答案冲突，已保留本地题库：{error}",*notes]
    if len(merged.questions)==len(existing.questions):
        return existing,notes
    try:
        save_bank(merged,cache)
    except OSError as error:
        notes.append(f"题库已载入，缓存保存失败：{error}")
    return merged,notes
