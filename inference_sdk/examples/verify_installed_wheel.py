"""Run without source imports, compiler, Python ORT, transformers or torch."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import numpy as np
import edge_ai_sdk
from edge_ai_sdk import InferenceSession

p = argparse.ArgumentParser()
p.add_argument("--model", required=True)
p.add_argument("--output", required=True)
args = p.parse_args()
session = InferenceSession(args.model)
inputs = np.arange(8,dtype=np.float32).reshape(2,4)
expected = inputs @ (np.arange(12,dtype=np.float32).reshape(4,3)/12)
actual = session.run({"input": inputs})["output"]
np.testing.assert_allclose(actual,expected,atol=1e-6)
report = {"platform": platform.platform(), "package_location_kind": "site-packages" if "site-packages" in edge_ai_sdk.__file__ else "source",
          "max_abs_error": float(np.max(np.abs(actual-expected))),
          "model_sha256": hashlib.sha256(Path(args.model).read_bytes()).hexdigest(),
          "numpy_version": np.__version__, "requires_python_ort": False}
assert report["package_location_kind"] == "site-packages"
Path(args.output).write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report))
