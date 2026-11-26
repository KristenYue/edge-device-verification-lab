"""Python tokenizer + native ONNX encoder, compatible with knowledge Embedder."""
import numpy as np

from .backends import NativeOrtBackend


class NativeEmbedder:
    def __init__(self, model_path, tokenizer_path):
        from transformers import AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(
            tokenizer_path, local_files_only=True
        )
        self.session = NativeOrtBackend(model_path)

    def encode(self, texts):
        if not texts:
            raise ValueError("expected 1..128 nonempty texts")
        invalid_text = any(
            not isinstance(text, str) or not text.strip() for text in texts
        )
        if len(texts) > 128 or invalid_text:
            raise ValueError("expected 1..128 nonempty texts")
        batch = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="np",
        )
        names = [entry["name"] for entry in self.session.model_info()["inputs"]]
        feed = {name: np.ascontiguousarray(batch[name], dtype=np.int64) for name in names}
        return self.session.run(feed)["embeddings"].tolist()
