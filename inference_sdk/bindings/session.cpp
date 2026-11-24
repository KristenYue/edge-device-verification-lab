#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <chrono>
#include <cstring>
#include <onnxruntime_cxx_api.h>
#include <filesystem>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;

namespace {

py::dict tensor_spec(const std::string& name, const Ort::TypeInfo& type) {
  const auto tensor = type.GetTensorTypeAndShapeInfo();
  py::dict spec;
  spec["name"] = name;
  spec["shape"] = py::cast(tensor.GetShape());
  spec["onnx_dtype"] = static_cast<int>(tensor.GetElementType());
  return spec;
}

bool numpy_dtype_matches(const py::dtype& dtype,
                         ONNXTensorElementDataType element_type) {
  switch (element_type) {
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT:
      return dtype.is(py::dtype::of<float>());
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_DOUBLE:
      return dtype.is(py::dtype::of<double>());
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64:
      return dtype.is(py::dtype::of<int64_t>());
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_INT32:
      return dtype.is(py::dtype::of<int32_t>());
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_UINT8:
      return dtype.is(py::dtype::of<uint8_t>());
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_INT8:
      return dtype.is(py::dtype::of<int8_t>());
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_BOOL:
      return dtype.is(py::dtype::of<bool>());
    default:
      return false;
  }
}

template <typename T>
py::array copy_tensor_output(const Ort::Value& value,
                             const std::vector<int64_t>& shape) {
  py::array_t<T> output(shape);
  std::memcpy(output.mutable_data(), value.GetTensorData<T>(), output.nbytes());
  return output;
}

py::array output_to_numpy(const Ort::Value& value) {
  const auto info = value.GetTensorTypeAndShapeInfo();
  const auto shape = info.GetShape();
  switch (info.GetElementType()) {
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT:
      return copy_tensor_output<float>(value, shape);
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_DOUBLE:
      return copy_tensor_output<double>(value, shape);
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64:
      return copy_tensor_output<int64_t>(value, shape);
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_INT32:
      return copy_tensor_output<int32_t>(value, shape);
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_UINT8:
      return copy_tensor_output<uint8_t>(value, shape);
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_INT8:
      return copy_tensor_output<int8_t>(value, shape);
    case ONNX_TENSOR_ELEMENT_DATA_TYPE_BOOL:
      return copy_tensor_output<bool>(value, shape);
    default:
      throw py::value_error("unsupported output dtype");
  }
}

}  // namespace

class InferenceSession {
  Ort::Env env{ORT_LOGGING_LEVEL_WARNING, "edge-ai"};
  Ort::SessionOptions options;
  std::unique_ptr<Ort::Session> session;
  std::vector<std::string> inputs, outputs;
public:
  explicit InferenceSession(const std::string& path) {
    options.SetIntraOpNumThreads(1);
    options.SetInterOpNumThreads(1);
    session = std::make_unique<Ort::Session>(env, std::filesystem::path(path).c_str(), options);
    Ort::AllocatorWithDefaultOptions allocator;
    for(size_t i=0;i<session->GetInputCount();++i)
      inputs.emplace_back(session->GetInputNameAllocated(i,allocator).get());
    for(size_t i=0;i<session->GetOutputCount();++i)
      outputs.emplace_back(session->GetOutputNameAllocated(i,allocator).get());
  }
  py::dict model_info() {
    py::list input_specs;
    for(size_t i=0;i<inputs.size();++i) {
      input_specs.append(tensor_spec(inputs[i], session->GetInputTypeInfo(i)));
    }
    py::list output_specs;
    for(size_t i=0;i<outputs.size();++i) {
      output_specs.append(tensor_spec(outputs[i], session->GetOutputTypeInfo(i)));
    }
    py::dict result; result["inputs"]=input_specs; result["outputs"]=output_specs;
    result["provider"]="CPUExecutionProvider";
    result["onnxruntime_version"]=OrtGetApiBase()->GetVersionString();
    return result;
  }
  py::dict run_impl(const py::dict& feed, py::dict* trace) {
    using Clock = std::chrono::steady_clock;
    const auto total_start = Clock::now();
    if(feed.size()!=inputs.size()) throw py::value_error("input names/count mismatch");
    std::vector<py::array> owners;
    std::vector<Ort::Value> tensors;
    std::vector<const char*> in_names,out_names;
    auto memory=Ort::MemoryInfo::CreateCpu(OrtArenaAllocator,OrtMemTypeDefault);
    for(size_t i=0;i<inputs.size();++i) {
      auto key=py::str(inputs[i]);
      if(!feed.contains(key)||!py::isinstance<py::array>(feed[key])) throw py::value_error("expected named NumPy array");
      auto array=py::cast<py::array>(feed[key]);
      if(!(array.flags()&py::array::c_style)) throw py::value_error("input must be C contiguous");
      auto type=session->GetInputTypeInfo(i);
      auto spec=type.GetTensorTypeAndShapeInfo();
      auto shape=spec.GetShape();
      if(static_cast<size_t>(array.ndim())!=shape.size()) throw py::value_error("input rank mismatch");
      for(size_t d=0;d<shape.size();++d) {
        if(shape[d]>=0&&shape[d]!=array.shape(d)) throw py::value_error("input dimension mismatch");
        shape[d]=array.shape(d);
      }
      auto dtype=spec.GetElementType();
      if(!numpy_dtype_matches(array.dtype(), dtype))
        throw py::value_error("unsupported or mismatched input dtype");
      owners.push_back(array); // Retain Python owners for the full native call.
      tensors.push_back(Ort::Value::CreateTensor(memory,const_cast<void*>(array.data()),array.nbytes(),shape.data(),shape.size(),dtype));
      in_names.push_back(inputs[i].c_str());
    }
    for(auto& name:outputs) out_names.push_back(name.c_str());
    const auto input_ready = Clock::now();
    std::vector<Ort::Value> values;
    Clock::time_point run_finished;
    {
      py::gil_scoped_release release; // No Python API inside this scope.
      values=session->Run(Ort::RunOptions{nullptr},in_names.data(),tensors.data(),tensors.size(),out_names.data(),out_names.size());
      run_finished = Clock::now();
    }
    py::dict result;
    for(size_t i=0;i<values.size();++i) {
      result[py::str(outputs[i])]=output_to_numpy(values[i]);
      // Each NumPy array owns its storage after the Ort::Value is destroyed.
    }
    const auto output_ready = Clock::now();
    if(trace != nullptr) {
      const auto micros = [](Clock::duration duration) {
        return std::chrono::duration<double, std::micro>(duration).count();
      };
      (*trace)["input_binding_us"] = micros(input_ready - total_start);
      (*trace)["ort_run_us"] = micros(run_finished - input_ready);
      (*trace)["output_copy_us"] = micros(output_ready - run_finished);
      (*trace)["total_us"] = micros(output_ready - total_start);
    }
    return result;
  }

  py::dict run(const py::dict& feed) { return run_impl(feed, nullptr); }

  py::dict run_profiled(const py::dict& feed) {
    py::dict trace;
    py::dict result;
    result["outputs"] = run_impl(feed, &trace);
    result["trace"] = trace;
    return result;
  }
};

PYBIND11_MODULE(_native,m) {
  py::register_exception<Ort::Exception>(m,"InferenceError");
  py::class_<InferenceSession>(m,"InferenceSession")
    .def(py::init<const std::string&>()).def("model_info",&InferenceSession::model_info)
    .def("run",&InferenceSession::run)
    .def("run_profiled",&InferenceSession::run_profiled);
}
