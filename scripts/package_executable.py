"""Package a verified PyInstaller directory without local personnel or settings."""
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from newxky.default_bank import BUNDLE_DIRECTORY,DEFAULT_PDF_NAME,CACHE_NAME,MANIFEST_NAME,prepare_bundle


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--default-bank',type=Path,default=ROOT/BUNDLE_DIRECTORY/DEFAULT_PDF_NAME)
    args=parser.parse_args()
    app=args.app_dir.resolve()
    output=args.output.resolve()
    dist=(ROOT/'dist').resolve()
    if not dist.is_relative_to(ROOT.resolve()):
        parser.error('The dist directory must remain within this workspace')
    if not app.is_relative_to(dist) or not output.is_relative_to(dist):
        parser.error('Application and archive must be inside this project dist directory')
    if not (app/'NewXKY.exe').is_file() or not (app/'_internal').is_dir():
        parser.error('Build the standalone executable first')
    bundled=prepare_bundle(args.default_bank,app/BUNDLE_DIRECTORY)
    for name,target in [('README.md','使用说明.md'),('验证记录.md','验证记录.md'),
                        ('THIRD_PARTY_NOTICES.md','THIRD_PARTY_NOTICES.md')]:
        shutil.copy2(ROOT/name,app/target)
    (app/'使用说明.txt').write_text(
        'NewXKY 免安装版\n\n'
        '1. 完整解压 ZIP 后双击 NewXKY.exe。保留 _internal 文件夹。\n'
        '2. 已附带指定 PDF 题库，启动时自动加载；选择“自动加载文件夹…”配置人员 Excel 目录。\n'
        '3. 启动时加载所选目录这一层的全部 xlsx，按区县、姓名、身份证号共同去重。\n'
        '4. 在备选和待考列表之间双向拖拽，待考内部可拖动排序。\n'
        '5. 手动开考并完成验证，框入完整题干、选项和底部按钮，启动自动答题。\n'
        '6. 确认交卷成功后累计计数增加；重复通知不加数，重启继续累计。\n\n'
        '每日及总的已完成、未完成 Excel 位于“人员记录/已完成”和“人员记录/未完成”。\n'
        '点击“记录”或“结果文件夹”查看。Excel 占用时另存最新更新文件。\n'
        '备选和待考列表均分行显示完整身份证号，可按姓名、区县或身份证号搜索。\n'
        '更新软件时保留 data 和人员记录文件夹。随包 PDF 及缓存位于题库文件夹。\n'
        '包内包含本地 OCR 模型和运行库，无需安装 Python。\n',encoding='utf-8')
    revision=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    status=subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True,check=True).stdout
    sources=[ROOT/'main.py',*sorted((ROOT/'newxky').glob('*.py'))]
    metadata={'format':'PyInstaller onedir','platform':'Windows x64','built_at':datetime.now().isoformat(timespec='seconds'),
              'source_revision':revision,'source_modified':bool(status.strip()),'python':platform.python_version(),
              'exe_sha256':digest(app/'NewXKY.exe'),'default_bank':bundled,
              'source_sha256':{str(path.relative_to(ROOT)).replace('\\','/'):digest(path) for path in sources}}
    (app/'build-info.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    files=[app/'NewXKY.exe',*(path for path in (app/'_internal').rglob('*') if path.is_file() and '__pycache__' not in path.parts)]
    files.extend(app/name for name in ('使用说明.md','使用说明.txt','验证记录.md','THIRD_PARTY_NOTICES.md','build-info.json'))
    files.extend(app/BUNDLE_DIRECTORY/name for name in (bundled['pdf'],CACHE_NAME,MANIFEST_NAME))
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_name(output.name+'.'+uuid4().hex+'.partial')
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for path in sorted(files):
                archive.write(path,(Path('NewXKY')/path.relative_to(app)).as_posix())
        print('ZIP_CREATED_CHECKING',len(files),flush=True)
        with zipfile.ZipFile(temporary) as archive:
            assert archive.testzip() is None
            assert all(Path(name).parts[1] not in {'data','人员记录','人员结果'} for name in archive.namelist())
            assert 'NewXKY/NewXKY.exe' in archive.namelist()
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    checksum=digest(output)
    output.with_suffix(output.suffix+'.sha256').write_text(f'{checksum}  {output.name}\n',encoding='utf-8')
    print('PORTABLE_READY',str(output),output.stat().st_size,checksum,flush=True)


if __name__=='__main__':
    main()
