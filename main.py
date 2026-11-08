"""NewXKY entry point."""
from __future__ import annotations


def main():
    import argparse
    from multiprocessing import freeze_support

    freeze_support()
    parser = argparse.ArgumentParser(description="NewXKY 区域答题助手")
    parser.add_argument("--data-dir", help="授权记录和区域设置的保存目录")
    parser.add_argument("--hide-console", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-check", nargs=2, metavar=("IMAGE", "REPORT"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_check:
        from newxky.selfcheck import self_check
        return self_check(*args.self_check)
    from newxky.ui import run
    return run(args.data_dir, hide_console=args.hide_console)


if __name__ == "__main__":
    raise SystemExit(main())
