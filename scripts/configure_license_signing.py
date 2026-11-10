"""Create or reuse a server signing key and embed only its public key in the client."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from license_server.signing import KEY_NAME, load_key, public_key_text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", type=Path, default=ROOT / "license_server/data" / KEY_NAME)
    args = parser.parse_args()
    path = args.key.resolve()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        with path.open("xb") as stream:
            stream.write(pem)
        if sys.platform != "win32":
            path.chmod(0o600)
    key = load_key(path)
    target = ROOT / "newxky/license_config.py"
    text = target.read_text(encoding="utf-8")
    assignment = f"LICENSE_PUBLIC_KEY = {public_key_text(key)!r}"
    if re.search(r"^LICENSE_PUBLIC_KEY\s*=.*$", text, re.M):
        text = re.sub(r"^LICENSE_PUBLIC_KEY\s*=.*$", assignment, text, flags=re.M)
    else:
        text = text.rstrip() + "\n" + assignment + "\n"
    target.write_text(text, encoding="utf-8")
    print("Signing configured. Private key kept in the server data directory; public key written to client config.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
