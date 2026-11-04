"""Run supplied exam screenshots through the same local OCR pipeline."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from io import BytesIO
from newxky.bank import read_bank
from newxky.matching import KnowledgeIndex
from newxky.ocr import LocalOCR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", type=Path, nargs="+", help="本地截图路径")
    parser.add_argument("--bank", type=Path, default=Path("data/bank.json"))
    parser.add_argument("--crop", type=int, nargs=4, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    parser.add_argument("--output", type=Path, default=Path("tmp/validation/screenshot-results.json"))
    parser.add_argument("--expect", action="append", help="每张图的预期状态和字母，如 matched:B 或 reference:ABC；按图片顺序重复提供")
    args = parser.parse_args()
    if args.expect and len(args.expect) != len(args.images):
        parser.error("--expect 数量必须与截图数量相同")
    bank = read_bank(args.bank)
    if not bank.questions:
        parser.error("题库缓存为空，请先在软件内导入 PDF")
    index = KnowledgeIndex(bank.questions)
    engine = LocalOCR()
    results = []
    for i, path in enumerate(args.images, 1):
        im = Image.open(path)
        crop = im.crop(tuple(args.crop)) if args.crop else im
        content = BytesIO()
        crop.save(content, format="PNG")
        text = engine.recognize(content.getvalue())
        match = index.lookup(text)
        result = {"screenshot": i, "status": match.status, "answers": match.answers,
                  "bank_number": match.question.number if match.question else None, "text": text}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.expect:
        for result, expected in zip(results, args.expect):
            status, answers = expected.split(":", 1)
            assert result["status"] == status and "".join(result["answers"]) == answers, result


if __name__ == "__main__":
    main()
