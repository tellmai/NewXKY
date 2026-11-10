import importlib.util
import json
import sys
from pathlib import Path

import pytest


def packager(tmp_path,monkeypatch):
    path=Path(__file__).resolve().parents[1]/'scripts/package_executable.py'
    spec=importlib.util.spec_from_file_location('review_packager',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module,'ROOT',tmp_path)
    app=tmp_path/'dist/app'
    app.mkdir(parents=True)
    (app/'NewXKY.exe').write_bytes(b'synthetic executable')
    (app/'_internal').mkdir()
    bank=tmp_path/'题库'
    bank.mkdir()
    (bank/module.SOURCE_PDF_NAME).write_bytes(b'synthetic source PDF')
    (bank/'default-bank.json').write_text('{"version":1}',encoding='utf-8')
    manifest={'pdf':module.SOURCE_PDF_NAME,
              'pdf_sha256':module.digest(bank/module.SOURCE_PDF_NAME),
              'cache_sha256':module.digest(bank/'default-bank.json')}
    (bank/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    config={'license_server_url':module.LICENSE_SERVER_URL,
            'license_public_key':module.LICENSE_PUBLIC_KEY,
            'version':module.VERSION,'bank_sha256':manifest['cache_sha256']}
    (app/'build-config.json').write_text(json.dumps(config),encoding='utf-8')
    monkeypatch.setattr(sys,'argv',['package_executable.py','--app-dir',str(app)])
    return module,app,bank


@pytest.mark.parametrize('damage',['pdf','cache','version','built_bank'])
def test_release_rejects_stale_pdf_cache_or_executable(tmp_path,monkeypatch,damage,capsys):
    module,app,bank=packager(tmp_path,monkeypatch)
    if damage=='pdf':
        (bank/module.SOURCE_PDF_NAME).write_bytes(b'changed source PDF')
    elif damage=='cache':
        (bank/'default-bank.json').write_text('changed cache',encoding='utf-8')
    else:
        config=json.loads((app/'build-config.json').read_text())
        config['version' if damage=='version' else 'bank_sha256']='old build'
        (app/'build-config.json').write_text(json.dumps(config),encoding='utf-8')
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code==2
    assert not list((tmp_path/'dist').glob('*.zip'))


def test_build_source_is_the_requested_pdf():
    from newxky.default_bank import SOURCE_PDF_NAME
    assert SOURCE_PDF_NAME=='2026年度知识考试复习资料.pdf'
