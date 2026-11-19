"""Export locally cached pretrained BGE: tokenizer Python, encoder/CLS/L2 ONNX."""
import argparse
import hashlib
import json
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    encoder = AutoModel.from_pretrained(args.model, local_files_only=True, low_cpu_mem_usage=False).eval()

    class Embedding(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = encoder

        def forward(self, input_ids, attention_mask, token_type_ids):
            values = self.encoder(input_ids=input_ids, attention_mask=attention_mask,
                                  token_type_ids=token_type_ids).last_hidden_state[:, 0]
            return torch.nn.functional.normalize(values, p=2, dim=1)

    inputs = tokenizer(["设备安全联锁触发，禁止启动", "查询机器人巡检任务状态"], padding=True, return_tensors="pt")
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    names = ["input_ids", "attention_mask", "token_type_ids"]
    torch.onnx.export(Embedding().eval(), tuple(inputs[name] for name in names), str(out),
                      input_names=names, output_names=["embeddings"], opset_version=17,
                      dynamic_axes={**{n: {0: "batch", 1: "sequence"} for n in names},
                                    "embeddings": {0: "batch"}}, dynamo=False)
    tokenizer.save_pretrained(out.parent / "tokenizer")
    metadata = {"model": "BAAI/bge-small-zh-v1.5", "snapshot": Path(args.model).name,
                "pooling": "CLS + L2", "provider": "CPU", "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                "torch": torch.__version__, "data_boundary": "pretrained_encoder_not_finetuned"}
    out.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
