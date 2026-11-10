import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_server.signing import KEY_NAME, load_key, public_key_text


def script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_configuration_reuses_private_key_and_preserves_public_key_when_url_changes(tmp_path, monkeypatch):
    config = tmp_path / "newxky/license_config.py"
    config.parent.mkdir()
    config.write_text('LICENSE_SERVER_URL = "https://old.example.org"\nLICENSE_PUBLIC_KEY = ""\n')
    configure = script("configure_license_signing")
    monkeypatch.setattr(configure, "ROOT", tmp_path)
    key = tmp_path / "private" / KEY_NAME
    monkeypatch.setattr(sys, "argv", ["configure", "--key", str(key)])
    assert configure.main() == 0
    private_bytes = key.read_bytes()
    public = public_key_text(load_key(key))
    assert configure.main() == 0
    assert key.read_bytes() == private_bytes
    setter = script("set_license_url")
    monkeypatch.setattr(setter, "TARGET", config)
    monkeypatch.setattr(sys, "argv", ["set-url", "https://license.example.org"])
    assert setter.main() == 0
    text = config.read_text(encoding="utf-8")
    assert public in text and "https://license.example.org" in text
    assert "PRIVATE KEY" not in text


@pytest.mark.parametrize("matching_key", [True, False])
def test_server_upgrade_preserves_live_database_and_requires_matching_signing_key(tmp_path, monkeypatch, matching_key):
    service = tmp_path / "license_server"
    service.mkdir()
    (service / "server.py").write_text("# server")
    (service / "signing.py").write_text("# signing")
    key = Ed25519PrivateKey.generate()
    key_path = service / KEY_NAME
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    module = script("package_server")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "LICENSE_PUBLIC_KEY", public_key_text(
        key if matching_key else Ed25519PrivateKey.generate()))
    output = tmp_path / "dist/update.zip"
    monkeypatch.setattr(sys, "argv", ["package", "--upgrade-only", "--signing-key", str(key_path),
                                     "--output", str(output)])
    if not matching_key:
        with pytest.raises(SystemExit) as caught:
            module.main()
        assert caught.value.code == 2
        assert not output.exists()
        return
    assert module.main() == 0
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert not any(name.endswith("licenses.db") for name in names)
        assert any(name.endswith("data/" + KEY_NAME) for name in names)
        info = json.loads(archive.read("NewXKY-LicenseServer/build-info.json"))
        assert info["upgrade_only"] is True
        assert info["database"] is None
        assert info["license_public_key"] == public_key_text(key)


@pytest.mark.parametrize("damage", ["source", "bank", "unexpected_module"])
def test_runtime_reuse_rejects_stale_sources_or_a_different_bank(tmp_path, monkeypatch, damage):
    module = script("package_runtime")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "newxky").mkdir()
    (tmp_path / "assets").mkdir()
    (tmp_path / module.BUNDLE_DIRECTORY).mkdir()
    for name in ["main.py", "portable_start.py", "newxky/__init__.py", "README.md", "THIRD_PARTY_NOTICES.md",
                 module.BUNDLE_DIRECTORY + "/" + module.CACHE_NAME,
                 module.BUNDLE_DIRECTORY + "/manifest.json"]:
        (tmp_path / name).write_text("current source " + name, encoding="utf-8")
    app = tmp_path / "app"
    app.mkdir()
    module.copy_sources(app)
    module.verify_reusable_sources(app)
    target = {"source": app / "newxky/__init__.py", "bank": app / module.BUNDLE_DIRECTORY / module.CACHE_NAME,
              "unexpected_module": app / "newxky/old_automation.py"}[damage]
    target.write_text("old build contents", encoding="utf-8")
    with pytest.raises(SystemExit, match="当前分支不一致"):
        module.verify_reusable_sources(app)
