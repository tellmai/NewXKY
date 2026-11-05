from newxky.lifetime import startup_allowed


def main():
    if not startup_allowed():
        return 0
    import argparse
    from multiprocessing import freeze_support

    freeze_support()
    parser = argparse.ArgumentParser(description="NewXKY 区域答题助手")
    parser.add_argument("--data-dir", help="题库和区域设置的保存目录")
    parser.add_argument("--hide-console", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-check", metavar="REPORT", help=argparse.SUPPRESS)
    parser.add_argument("--pdf", help=argparse.SUPPRESS)
    parser.add_argument("--image", help=argparse.SUPPRESS)
    parser.add_argument("--crop", type=int, nargs=4, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_check:
        from newxky.diagnostics import self_check
        return self_check(args.self_check, args.pdf, args.image, args.crop)
    from newxky.ui import run
    return run(args.data_dir, hide_console=args.hide_console)


if __name__ == "__main__":
    raise SystemExit(main())
