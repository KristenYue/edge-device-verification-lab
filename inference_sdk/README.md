# Edge AI Inference SDK｜C++ / Python 原生模型执行接口

[返回项目总览](../README.md) · [联合应用](https://github.com/KristenYue/telecom-network-incident-agent/blob/main/docs/evidence/native-llm-live.json) · [Ubuntu 验收](https://github.com/KristenYue/edge-device-verification-lab/actions/runs/44506857643)

**C++17 · pybind11 · ONNX Runtime CPU · Typed Backend / Tensor Contract · 有界异步请求 · CMake / scikit-build-core**

Python 应用通过 NumPy 调用 C++ 封装的 ONNX Session。分词与业务编排留在 Python；SDK 管理模型元数据、Tensor 输入契约、原生执行、输出所有权和异常转换。上层知识工具直接使用 `NativeEmbedder`，形成模型接口到业务应用的证据链。

## 接口与生命周期

```mermaid
flowchart LR
    P[Python Tokenizer / 业务] --> N[NumPy 输入]
    N --> V[输入名 / dtype / rank / shape / stride]
    V --> S[C++ Env / Options / Session]
    S --> R[释放 GIL 执行 Run]
    R --> O[复制到 Python 自有输出]
    O --> K[Embedding 知识工具]
```

| 关键设计 | 实现与原因 |
|---|---|
| Session 资源所有权 | Session 独立持有 Env 与 Options，确保析构依赖顺序；不依赖 Python 临时对象维持原生会话 |
| Tensor 严格契约 | 校验输入名、rank、固定/动态维度、C-contiguous与ONNX dtype；支持多输入、多输出及常用数值输出类型，拒绝隐式类型转换 |
| 稳定模型契约 | `ModelContract` / `TensorSpec` 将原生元数据转换成可序列化接口，显式给出NumPy dtype和动态轴；错误精确到输入名与维度 |
| 可替换执行后端 | `InferenceBackend` Protocol隔离调度层与执行引擎；`NativeOrtBackend`是当前原生实现，后续CUDA EP/NPU适配无需改写异步队列 |
| GIL 与输入生命周期 | Run 调用期间保留 NumPy 所有者引用，只在原生执行段释放 GIL；调用者不得并发修改输入 |
| 输出生命周期 | 结果复制到 Python 拥有的数组，Session 或 ORT 临时输出销毁后仍可读 |
| 有界异步请求 | 固定 Worker 数和等待队列容量；提交时复制输入；队列满、取消、排队超时和执行超时具有独立语义 |
| 运行统计 | `SessionStats`累计admitted/rejected/completed/cancelled/timed_out/failed，并计算当前in-flight，便于容量与失败分析 |
| 阶段 Trace | `run_profiled` 使用 C++ 单调时钟拆分输入绑定、ORT执行、输出复制与总时间；与异步请求的排队/执行时间形成两层 Trace |
| 异常边界 | 参数错误为 `ValueError`，ORT 执行错误映射 `InferenceError` |
| 可安装交付 | Wheel 携带运行库，Windows / Linux 干净环境独立安装执行；Linux 补齐 SONAME 别名 |

## 预训练 BGE 实测

模型 `BAAI/bge-small-zh-v1.5`，snapshot `7999e1d3359715c523056ef9478215996d62a620`，CLS + L2 归一化，ONNX 动态 batch / sequence；Python 分词截断 256 token。

| 项目 | C++ SDK | Python ORT | 口径 |
|---|---:|---:|---|
| 输出形状 | 3×512 | 3×512 | 输入 3×15 |
| 最大绝对误差 | **1.527×10⁻⁷** | 参考 | 数值对齐 |
| P50 | 13.33 ms | 12.69 ms | 单线程，预热 5 次、测量 30 次 |
| P95 | 14.86 ms | 14.15 ms | 不含分词 |

[原始数据](benchmarks/windows-bge.json)。原生 ORT 1.22.0、Python ORT 1.32.0。本轮没有获得提速；交付价值是**跨语言契约、生命周期安全、可安装接口和业务集成**。

## CPU 动态 INT8：性能收益与质量退化同时保留

同一 BGE ONNX 模型、相同冻结输入、单线程 CPU Execution Provider；动态 INT8 由 ONNX Runtime 提供的权重量化生成，不是自研量化算法或算子。独立进程分别测量 FP32 与 INT8，避免前一个 Session 的内存池污染后一个 RSS 结果。

| 指标 | FP32 | 动态 INT8 | 结论 |
|---|---:|---:|---|
| 模型文件 | 94.86 MB | 23.94 MB | 减少 74.8% |
| P50 / P95 / P99 | 128.31 / 131.13 / 131.39 ms | 48.29 / 51.78 / 52.40 ms | P50 约 2.66× |
| 吞吐 | 93.5 items/s | 248.5 items/s | 约 2.66× |
| 峰值 RSS | 223.0 MB | 119.4 MB | 明显下降 |
| 冻结检索小样本 Recall@1 | 1.00 | 0.50 | **质量退化，不接受为默认部署配置** |
| 平均 / 最低余弦相似度 | 参考 | 0.9635 / 0.9556 | 数值接近不等于任务质量保持 |

冻结集只有 8 篇文档和 4 个查询，仅用于回归烟雾检查，不能解释成生产检索精度。该结果说明不能只用延迟和模型体积决定是否部署 INT8；后续必须扩大代表性数据集，分析量化算子覆盖，并在具备校准语料后评估静态量化或其他精度策略。[原始报告](benchmarks/windows-bge-dynamic-int8.json) · [可复现实验脚本](examples/benchmark_dynamic_int8.py)

## 有界异步请求：吞吐、排队与执行竞争

使用同一 FP32 BGE、12×48 输入、单个共享 Session，对 24 个同时提交的请求进行突发压力实验。端到端时间包含提交时输入复制、排队和原生执行；吞吐包含提交、排队、执行与结果回收。

| Worker | 吞吐 | Queue P95 | Execution P50 / P95 | End-to-end P95 |
|---:|---:|---:|---:|---:|
| 同步基线 | 7.91 req/s | — | 126.77 / 129.80 ms | — |
| 1 | 7.79 req/s | 2804.17 ms | 127.87 / 131.26 ms | 2933.12 ms |
| 2 | 15.05 req/s | 1426.19 ms | 131.51 / 139.14 ms | 1559.47 ms |
| 4 | 25.89 req/s | 749.02 ms | 144.82 / 173.32 ms | 908.80 ms |

增加 Worker 提高了突发吞吐并缩短排队，但单次执行延迟因 CPU 资源竞争上升；因此不能只报告约 3.27× 的吞吐变化。实验同时验证容量耗尽返回 `QueueFullError`、排队请求可取消、0.1 ms 截止时间导致执行结果被丢弃。每个请求的 submitted/started/completed 时间线保存在原始 JSON 中。[原始报告](benchmarks/windows-bge-async.json) · [实验脚本](examples/benchmark_async_session.py)

## 跨模型与动态 Batch 矩阵

在相同单线程 CPU 配置下，使用真实 BGE、ONNX Model Zoo MobileNetV2，以及只用于接口验证的动态双输入/双输出图。每个配置在三个独立子进程中分别预热 5 次、测量 30 次，表格报告三个试验统计量的中位数，并与 Python ORT 输出逐项对齐。

| Workload | Batch | Native P50 / P95 | Native吞吐 | Python ORT P50 | 数值结果 |
|---|---:|---:|---:|---:|---|
| BGE | 1 | 11.66 / 14.41 ms | 85.8 items/s | 11.36 ms | allclose |
| BGE | 4 | 43.09 / 47.09 ms | 92.8 items/s | 42.02 ms | allclose |
| BGE | 12 | 125.52 / 132.13 ms | 95.6 items/s | 123.49 ms | allclose |
| MobileNetV2 | 1 | 6.03 / 7.42 ms | 165.8 items/s | 6.56 ms | allclose |
| MobileNetV2 | 4 | 24.55 / 28.59 ms | 162.9 items/s | 25.95 ms | allclose |

本轮中位数显示 BGE 吞吐随 Batch 增大而提高，但收益逐步收窄；MobileNet Batch 1 三轮吞吐范围为 150.5–177.3 items/s，说明本机波动足以影响相邻配置排序。因此 SDK 不把“增大 Batch”当作固定优化结论，选择仍需结合延迟预算和重复试验。生成参考图的微秒级结果只证明多输入、多输出、动态维度和整数输出契约，不与真实模型性能混报。Native ORT 1.22 与 Python ORT 1.32 版本不同，二者差异也不能简单解释为 pybind11 开销。[原始矩阵](benchmarks/windows-model-matrix.json) · [实验脚本](examples/benchmark_model_matrix.py) · [模型来源和哈希](models/README.md)

原生 `run_profiled` 进一步分解输入绑定、ORT执行与输出复制。上述真实模型的输入绑定 P50 为 18.7–23.9 μs，输出复制 P50 为 18.2–23.8 μs；总时间几乎全部来自 ORT 执行。这个结果说明当前CPU工作负载不值得优先优化pybind11数据绑定，但不外推到大输出、非连续输入或GPU拷贝场景。

![BGE 真实数值对齐与延迟对照](../docs/assets/sdk-evidence.png)

## 从组件到应用的证据

| 层次 | 结果 | 证据 |
|---|---|---|
| 参考计算图 | 与 NumPy 最大误差 0；dtype / shape / stride 非法输入拒绝；输出不依赖 Session 存活 | [Windows 参考验证](benchmarks/windows-reference.json) |
| 干净安装 | 只安装 NumPy 和 SDK Wheel，无 Python ORT / Torch / Transformers，参考图误差 0 | [Windows 干净环境](benchmarks/windows-clean-install.json) |
| Ubuntu Wheel | 编译、参考图执行、独立虚拟环境安装成功 | [Linux CI](https://github.com/KristenYue/edge-device-verification-lab/actions/runs/44506857643) |
| 预训练模型 | BGE 原生执行与 Python ORT 对齐 | [BGE 记录](benchmarks/windows-bge.json) |
| 业务工具 | NativeEmbedder 接入知识库，保存来源、版本与后端标记 | [检索记录](https://github.com/KristenYue/telecom-network-incident-agent/blob/main/docs/evidence/native-retrieval.json) |
| 真实模型联合链路 | LLM 查询 C++ 设备，再调用原生 ONNX 知识工具并生成诊断 | [联合轨迹](https://github.com/KristenYue/telecom-network-incident-agent/blob/main/docs/evidence/native-llm-live.json) |

## 构建与运行

在仓库根目录执行；先取得官方 ONNX Runtime CPU C/C++ 包，目录包含 `include/` 与 `lib/`。

```powershell
.\inference_sdk\build_windows.ps1 -OrtRoot <ORT发行包目录>
.\.venv-sdk\Scripts\python.exe inference_sdk/examples/verify_session.py --output .runtime/sdk-reference.json
```

Linux 使用同一 CMake / Wheel 工程，完整可执行命令见 [Linux 构建流程](../.github/workflows/inference-sdk.yml)。

```python
from edge_ai_sdk import NativeOrtBackend

backend = NativeOrtBackend("model.onnx")
print(backend.contract.to_dict())
outputs = backend.run({"input": input_array})
```

异步调用显式限制活跃请求与等待队列。截止时间覆盖排队和执行；已经进入 ONNX Runtime 的调用不能被强制抢占，超时后只丢弃结果，不声称中断底层执行。

```python
from edge_ai_sdk import AsyncInferenceSession, QueueFullError

with AsyncInferenceSession("model.onnx", max_workers=2, max_queue=8) as session:
    request = session.submit(
        {"input": input_array}, deadline_ms=100, enqueue_timeout_ms=5
    )
    outputs = request.result()
    print(request.metrics.queue_ms, request.metrics.execution_ms)
    print(session.stats())
```

`inference_sdk/tests/test_inference_sdk.py` 使用动态 Batch 的双输入/双输出图验证元数据、`float32`与`int64`输出，并用确定性阻塞会话验证队列容量、取消、输入副本和超时结果丢弃。Windows 本地测试已通过；Ubuntu workflow 已配置执行该测试集，需以对应 CI 运行结果为准。

[模型导出](examples/export_embedding.py) · [BGE 对齐与时延](examples/verify_embedding.py) · [干净安装验证](examples/verify_installed_wheel.py) · [原生源码](bindings/session.cpp)

Agent 联合演示需设置 `EDGE_AI_MODEL_PATH`、`EDGE_AI_TOKENIZER_PATH` 和模型服务环境变量，执行业务仓库 `scripts/demo_native_llm.py --simulator <设备可执行文件> --output <结果.json>`。模型权重独立取得，不随代码包发布。

## 工程复盘

Linux Wheel 的原生库存在 SONAME 运行时查找问题：编译通过不代表干净环境能加载。通过安装库别名并在全新虚拟环境执行参考图，验证完整打包路径。Windows 依赖通过微软官方 NuGet 取得，避免开发机隐式 DLL 路径掩盖缺失依赖。

当前可交付后端仍为 CPU Execution Provider；Backend Protocol证明的是接口解耦，不代表已经完成NPU/GPU适配。量化与自研算子属于不同适配范围。异步层当前位于 Python SDK，底层 `Run` 仍由 C++ 绑定执行并释放 GIL；尚未声称具备原生 C++ 调度器或可抢占推理。本页不将参考图延迟解释为预训练模型或目标芯片性能。


---

文档与结果口径：2026-11-26。SDK 0.3.0新增Backend Protocol、结构化Tensor契约和会话级结果统计；功能以对应源码和运行记录为准。
