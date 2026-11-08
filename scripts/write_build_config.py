"""Write build provenance without embedding Unicode paths in PowerShell -c."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from newxky import __version__
from newxky.default_bank import BUNDLE_DIRECTORY,CACHE_NAME
from newxky.license_config import LICENSE_SERVER_URL


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app_dir',type=Path)
    args=parser.parse_args()
    config={'license_server_url':LICENSE_SERVER_URL,'version':__version__,
            'bank_sha256':hashlib.sha256((ROOT/BUNDLE_DIRECTORY/CACHE_NAME).read_bytes()).hexdigest()}
    (args.app_dir/'build-config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
