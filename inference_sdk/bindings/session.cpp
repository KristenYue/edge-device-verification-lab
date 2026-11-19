#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <cstring>
#include <onnxruntime_cxx_api.h>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

namespace py = pybind11;

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
    py::list specs;
    for(size_t i=0;i<inputs.size();++i) {
      auto type=session->GetInputTypeInfo(i);
      auto tensor=type.GetTensorTypeAndShapeInfo();
      py::dict spec;
      spec["name"]=inputs[i]; spec["shape"]=py::cast(tensor.GetShape());
      spec["onnx_dtype"]=static_cast<int>(tensor.GetElementType()); specs.append(spec);
    }
    py::dict result; result["inputs"]=specs; result["outputs"]=py::cast(outputs);
    result["provider"]="CPUExecutionProvider"; return result;
  }
  py::dict run(const py::dict& feed) {
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
      bool valid=(dtype==ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT&&array.dtype().is(py::dtype::of<float>()))
              ||(dtype==ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64&&array.dtype().is(py::dtype::of<int64_t>()));
      if(!valid) throw py::value_error("unsupported or mismatched dtype (float32/int64 only)");
      owners.push_back(array); // Retain Python owners for the full native call.
      tensors.push_back(Ort::Value::CreateTensor(memory,const_cast<void*>(array.data()),array.nbytes(),shape.data(),shape.size(),dtype));
      in_names.push_back(inputs[i].c_str());
    }
    for(auto& name:outputs) out_names.push_back(name.c_str());
    std::vector<Ort::Value> values;
    {
      py::gil_scoped_release release; // No Python API inside this scope.
      values=session->Run(Ort::RunOptions{nullptr},in_names.data(),tensors.data(),tensors.size(),out_names.data(),out_names.size());
    }
    py::dict result;
    for(size_t i=0;i<values.size();++i) {
      auto info=values[i].GetTensorTypeAndShapeInfo();
      if(info.GetElementType()!=ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT) throw py::value_error("float32 output required");
      auto shape=info.GetShape();
      py::array_t<float> output(shape);
      std::memcpy(output.mutable_data(),values[i].GetTensorData<float>(),output.nbytes());
      result[py::str(outputs[i])]=output; // Copy owns storage after Ort::Value destruction.
    }
    return result;
  }
};

PYBIND11_MODULE(_native,m) {
  py::register_exception<Ort::Exception>(m,"InferenceError");
  py::class_<InferenceSession>(m,"InferenceSession")
    .def(py::init<const std::string&>()).def("model_info",&InferenceSession::model_info)
    .def("run",&InferenceSession::run);
}
