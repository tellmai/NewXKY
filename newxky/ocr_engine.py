"""Adapt the legacy and current RapidOCR APIs to a shared local model pipeline."""
from pathlib import Path
import os


class OCREngine:
    def __init__(self):
        threads = max(1, min(4, (os.cpu_count() or 2) // 2))
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ModuleNotFoundError as error:
            if error.name != "rapidocr_onnxruntime":
                raise
            from rapidocr import RapidOCR, OCRVersion, ModelType
            models = Path(__file__).resolve().parents[1] / "assets/ocr"
            required = {"Det": "ch_PP-OCRv4_det_infer.onnx", "Rec": "ch_PP-OCRv4_rec_infer.onnx",
                        "Cls": "ch_ppocr_mobile_v2.0_cls_infer.onnx"}
            if any(not (models / name).is_file() for name in required.values()):
                raise RuntimeError("便携包 OCR 模型不完整，请重新解压整个安装包")
            params = {"Global.text_score": 0.0, "Global.use_cls": False,
                      "EngineConfig.onnxruntime.intra_op_num_threads": threads,
                      "EngineConfig.onnxruntime.inter_op_num_threads": 1}
            for key, name in required.items():
                params[f"{key}.model_path"] = str(models / name)
                params[f"{key}.ocr_version"] = OCRVersion.PPOCRV4
                params[f"{key}.model_type"] = ModelType.MOBILE
            self.engine = RapidOCR(params=params)
            self.modern = True
        else:
            # Long and short lines padded together waste CPU on wide tensors.
            self.engine = RapidOCR(intra_op_num_threads=threads, inter_op_num_threads=1, rec_batch_num=1)
            self.modern = False

    def __call__(self, image, *, use_det=True):
        if not self.modern:
            result, _ = self.engine(image, use_det=use_det, use_cls=False, text_score=0.0)
            return result or []
        result = self.engine(image, use_det=use_det, use_cls=False, text_score=0.0)
        if result.txts is None:
            return []
        if not use_det:
            return [[text, score] for text, score in zip(result.txts, result.scores)]
        return [[box, text, score] for box, text, score in zip(result.boxes, result.txts, result.scores)]
