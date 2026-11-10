"""Set the public HTTPS license service address used by the release build."""
from __future__ import annotations

import argparse
import ast
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "newxky" / "license_config.py"
TEMPLATE = '''"""Build-time license service address.

The release build must contain the public HTTPS address of the NewXKY license
service. Keep this value empty in source control; a packaged application with
an empty value cannot activate and shows a configuration error instead.
"""

LICENSE_SERVER_URL = {url!r}  # Set to the public HTTPS address before building a release.
LICENSE_PUBLIC_KEY = {public_key!r}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="public HTTPS address, for example https://license.example.com")
    args = parser.parse_args()
    address = args.url.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(address)
    if parsed.scheme != "https" or not parsed.hostname:
        parser.error("address must start with https:// and include a hostname")
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"} or "example.com" in address.lower():
        parser.error("address must be the real public license service")
    public_key = ""
    for node in ast.parse(TARGET.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "LICENSE_PUBLIC_KEY" for target in node.targets
        ):
            public_key = ast.literal_eval(node.value)
    TARGET.write_text(TEMPLATE.format(url=address, public_key=public_key), encoding="utf-8")
    print(f"LICENSE_SERVER_URL={address}")
    print("Rebuild with scripts/build.ps1, then package with scripts/package_executable.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
