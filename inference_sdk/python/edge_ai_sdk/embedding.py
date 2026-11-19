"""Python tokenizer + native ONNX encoder, compatible with knowledge Embedder."""
import numpy as np

from . import InferenceSession


class NativeEmbedder:
    def __init__(self, model_path, tokenizer_path):
        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)
        self.session = InferenceSession(str(model_path))

    def encode(self, texts):
        if not texts or len(texts) > 128 or any(not isinstance(t, str) or not t.strip() for t in texts):
            raise ValueError("expected 1..128 nonempty texts")
        batch = self.tokenizer(texts, padding=True, truncation=True, max_length=256, return_tensors="np")
        names = [entry["name"] for entry in self.session.model_info()["inputs"]]
        feed = {name: np.ascontiguousarray(batch[name], dtype=np.int64) for name in names}
        return self.session.run(feed)["embeddings"].tolist()
