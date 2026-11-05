"""Adapt the legacy and current RapidOCR APIs to a shared local model pipeline."""
from pathlib import Path
import os
import hashlib
from collections import OrderedDict


class CachedRecognizer:
    """Cache exact detected line crops, including unchanged options/footer.

    Hash both dimensions and original bytes: similar glyphs, negations and
    decimals must never share a cache entry. No image contents are retained.
    """
    def __init__(self,recognizer,limit=256):
        self.recognizer = recognizer
        self.limit = limit
        self.cache = OrderedDict()
        self.hits = self.misses = 0

    def __getattr__(self,name):
        return getattr(self.recognizer,name)

    def __call__(self,images,return_word_box=False):
        if return_word_box:
            return self.recognizer(images,return_word_box)
        import numpy as np
        images = [images] if isinstance(images,np.ndarray) else images
        keys = [(image.shape,hashlib.blake2b(image.tobytes(),digest_size=16).digest()) for image in images]
        missing = list(dict.fromkeys(key for key in keys if key not in self.cache))
        elapsed = 0
        self.hits += len(keys)-len(missing)
        self.misses += len(missing)
        if missing:
            positions = {key:i for i,key in enumerate(keys)}
            values,elapsed = self.recognizer([images[positions[key]] for key in missing],False)
            for key,value in zip(missing,values):
                self.cache[key] = value
        result = []
        for key in keys:
            result.append(self.cache[key])
            self.cache.move_to_end(key)
        while len(self.cache)>self.limit:
            self.cache.popitem(last=False)
        return result,elapsed


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
            self.engine.text_rec = CachedRecognizer(self.engine.text_rec)
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
