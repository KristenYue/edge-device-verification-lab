# Local model assets

Model weights are intentionally excluded from Git. Benchmark reports identify every model by SHA-256.

## BGE small Chinese

- Model: `BAAI/bge-small-zh-v1.5`
- Frozen snapshot: `7999e1d3359715c523056ef9478215996d62a620`
- Local ONNX SHA-256: `1005e14a3a75167ac4082f3e0e31a8c060a5c9f5941b2af82232b276783357c5`
- Export path: run `../examples/export_embedding.py` with the separately downloaded snapshot.

The repository does not redistribute Hugging Face weights or tokenizer files.

## MobileNetV2

- Source: ONNX Model Zoo, `validated/vision/classification/mobilenet/model/mobilenetv2-12.onnx`
- License stated by the source: Apache 2.0
- Expected SHA-256: `c0c3f76d93fa3fd6580652a45618618a220fced18babf65774ed169de0432ad5`

```powershell
curl.exe -L `
  "https://github.com/onnx/models/raw/main/validated/vision/classification/mobilenet/model/mobilenetv2-12.onnx" `
  -o ".\inference_sdk\models\mobilenetv2-12.onnx"
```

Verify the hash before using the model in a benchmark.
