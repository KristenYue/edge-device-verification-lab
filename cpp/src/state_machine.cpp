#include "edge/state_machine.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <stdexcept>
#include <thread>

namespace edge {
namespace {

std::int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
               std::chrono::system_clock::now().time_since_epoch())
        .count();
}

int parse_int(const std::map<std::string, std::string>& params, const std::string& key,
              int fallback) {
    const auto it = params.find(key);
    if (it == params.end()) return fallback;
    try {
        std::size_t consumed = 0;
        const int value = std::stoi(it->second, &consumed);
        if (consumed != it->second.size()) throw std::invalid_argument("trailing characters");
        return value;
    } catch (...) {
        throw std::invalid_argument(key + " must be an integer");
    }
}

double parse_double(const std::map<std::string, std::string>& params,
                    const std::string& key, double fallback) {
    const auto it = params.find(key);
    if (it == params.end()) return fallback;
    try {
        std::size_t consumed = 0;
        const double value = std::stod(it->second, &consumed);
        if (consumed != it->second.size() || !std::isfinite(value)) {
            throw std::invalid_argument("invalid number");
        }
        return value;
    } catch (...) {
        throw std::invalid_argument(key + " must be a finite number");
    }
}

}  // namespace

std::string to_string(State state) {
    switch (state) {
        case State::Boot: return "BOOT";
        case State::Idle: return "IDLE";
        case State::Homing: return "HOMING";
        case State::Homed: return "HOMED";
        case State::Calibrating: return "CALIBRATING";
        case State::Ready: return "READY";
        case State::Running: return "RUNNING";
        case State::Complete: return "COMPLETE";
        case State::Warning: return "WARNING";
        case State::Error: return "ERROR";
        case State::EmergencyStop: return "E_STOP";
        case State::Recovering: return "RECOVERING";
    }
    return "UNKNOWN";
}

std::string to_string(CommunicationState state) {
    return state == CommunicationState::Online ? "ONLINE" : "OFFLINE";
}

std::string to_string(ControlMode mode) {
    return mode == ControlMode::Remote ? "REMOTE" : "LOCAL";
}

DeviceRuntime::DeviceRuntime() = default;

State DeviceRuntime::state() const noexcept { return state_; }
std::string DeviceRuntime::state_name() const { return to_string(state_); }
const std::vector<Event>& DeviceRuntime::events() const noexcept { return events_; }
std::uint64_t DeviceRuntime::run_count() const noexcept { return run_count_; }
bool DeviceRuntime::profile_loaded() const noexcept { return profile_.has_value(); }
CommunicationState DeviceRuntime::communication_state() const noexcept {
    return communication_state_;
}
ControlMode DeviceRuntime::control_mode() const noexcept { return control_mode_; }

void DeviceRuntime::record(State from, State to, const std::string& event,
                       const std::string& correlation_id, const std::string& detail) {
    events_.push_back(Event{next_sequence_++, now_ms(), correlation_id, event,
                            to_string(from), to_string(to), detail});
}

Result DeviceRuntime::reject(const std::string& code, const std::string& message) const {
    return Result{false, code, message, state_, {}};
}

Result DeviceRuntime::transition(State target, const std::string& code,
                             const std::string& message,
                             const std::string& correlation_id) {
    const State from = state_;
    state_ = target;
    record(from, target, code, correlation_id, message);
    return Result{true, code, message, state_, {}};
}

Result DeviceRuntime::load_profile(const std::map<std::string, std::string>& params,
                              const std::string& correlation_id) {
    if (state_ != State::Ready && state_ != State::Complete) {
        return reject("INVALID_STATE", "profile can only be loaded in READY or COMPLETE");
    }
    try {
        TaskProfile candidate;
        if (const auto it = params.find("name"); it != params.end()) candidate.name = it->second;
        candidate.sample_count = parse_int(params, "sample_count", 100);
        candidate.noise_sigma = parse_double(params, "noise_sigma", 0.02);
        candidate.drift_limit = parse_double(params, "drift_limit", 0.20);
        if (candidate.name.empty() || candidate.name.size() > 64) {
            return reject("PROFILE_INVALID", "name length must be between 1 and 64");
        }
        if (candidate.sample_count < 10 || candidate.sample_count > 100000) {
            return reject("PROFILE_INVALID", "sample_count must be between 10 and 100000");
        }
        if (candidate.noise_sigma < 0.0 || candidate.noise_sigma > 1.0) {
            return reject("PROFILE_INVALID", "noise_sigma must be between 0 and 1");
        }
        if (candidate.drift_limit <= 0.0 || candidate.drift_limit > 5.0) {
            return reject("PROFILE_INVALID", "drift_limit must be greater than 0 and at most 5");
        }
        profile_ = candidate;
        record(state_, state_, "PROFILE_LOADED", correlation_id, candidate.name);
        Result result{true, "PROFILE_LOADED", "profile accepted", state_, {}};
        result.data["profile"] = candidate.name;
        result.data["sample_count"] = std::to_string(candidate.sample_count);
        return result;
    } catch (const std::invalid_argument& exc) {
        return reject("PROFILE_INVALID", exc.what());
    }
}

Result DeviceRuntime::inject_fault(const std::map<std::string, std::string>& params,
                               const std::string& correlation_id) {
    const auto it = params.find("type");
    if (it == params.end()) return reject("FAULT_INVALID", "fault type is required");
    const std::string& type = it->second;
    if (type == "clear") {
        interlock_open_ = false;
        actuator_stuck_ = false;
        sensor_drift_ = false;
        response_delay_ms_ = 0;
        active_alarms_.clear();
        record(state_, state_, "FAULTS_CLEARED", correlation_id, "all injected faults cleared");
        return Result{true, "FAULTS_CLEARED", "all injected faults cleared", state_, {}};
    }
    if (type == "interlock_open") {
        interlock_open_ = true;
        active_alarms_.insert("ALARM-1001:INTERLOCK_OPEN");
    } else if (type == "actuator_stuck") {
        actuator_stuck_ = true;
        active_alarms_.insert("ALARM-2001:ACTUATOR_STUCK");
    } else if (type == "sensor_drift") {
        sensor_drift_ = true;
        active_alarms_.insert("ALARM-3001:SENSOR_DRIFT");
    }
    else if (type == "response_delay") {
        try {
            response_delay_ms_ = parse_int(params, "delay_ms", 250);
        } catch (const std::invalid_argument& exc) {
            return reject("FAULT_INVALID", exc.what());
        }
        if (response_delay_ms_ < 0 || response_delay_ms_ > 5000) {
            return reject("FAULT_INVALID", "delay_ms must be between 0 and 5000");
        }
    } else {
        return reject("FAULT_INVALID", "unsupported fault type");
    }
    record(state_, state_, "FAULT_INJECTED", correlation_id, type);
    return Result{true, "FAULT_INJECTED", type, state_, {{"fault_type", type}}};
}

Result DeviceRuntime::execute(const std::string& command,
                          const std::map<std::string, std::string>& params,
                          const std::string& correlation_id) {
    if (response_delay_ms_ > 0 && command != "inject_fault") {
        std::this_thread::sleep_for(std::chrono::milliseconds(response_delay_ms_));
    }
    if (command == "status") {
        return Result{true, "STATUS", "device status", state_,
                      {{"run_count", std::to_string(run_count_)},
                       {"profile_loaded", profile_ ? "true" : "false"},
                       {"interlock_open", interlock_open_ ? "true" : "false"},
                       {"communication_state", to_string(communication_state_)},
                       {"control_mode", to_string(control_mode_)}}};
    }
    if (command == "inject_fault") return inject_fault(params, correlation_id);
    if (command == "protocol_establish_communications") {
        communication_state_ = CommunicationState::Online;
        control_mode_ = ControlMode::Local;
        record(state_, state_, "COMMUNICATIONS_ESTABLISHED", correlation_id,
               "simplified control protocol communications established");
        return Result{true, "COMMUNICATIONS_ESTABLISHED", "communications established", state_,
                      {{"communication_state", "ONLINE"}, {"control_mode", "LOCAL"}}};
    }
    if (command == "protocol_go_offline") {
        communication_state_ = CommunicationState::Offline;
        control_mode_ = ControlMode::Local;
        record(state_, state_, "OFFLINE_ACK", correlation_id,
               "host requested offline");
        return Result{true, "OFFLINE_ACK", "device offline", state_,
                      {{"communication_state", "OFFLINE"}, {"control_mode", "LOCAL"}}};
    }
    if (command == "protocol_set_remote" || command == "protocol_set_local") {
        if (communication_state_ != CommunicationState::Online) {
            return reject("PROTOCOL_OFFLINE", "control mode requires ONLINE communications");
        }
        control_mode_ = command == "protocol_set_remote" ? ControlMode::Remote : ControlMode::Local;
        const std::string code = control_mode_ == ControlMode::Remote
                                     ? "REMOTE_MODE_ACK"
                                     : "LOCAL_MODE_ACK";
        record(state_, state_, code, correlation_id, "control mode changed");
        return Result{true, code, "control mode changed", state_,
                      {{"communication_state", "ONLINE"},
                       {"control_mode", to_string(control_mode_)}}};
    }
    if (command == "protocol_get_variables") {
        if (communication_state_ != CommunicationState::Online) {
            return reject("PROTOCOL_OFFLINE", "variable request requires ONLINE communications");
        }
        return Result{true, "VARIABLE_REPORT", "status variables reported", state_,
                      {{"DEVICE_STATE", to_string(state_)},
                       {"CONTROL_MODE", to_string(control_mode_)},
                       {"RUN_COUNT", std::to_string(run_count_)},
                       {"PROFILE_LOADED", profile_ ? "true" : "false"}}};
    }
    if (command == "protocol_get_alarms") {
        if (communication_state_ != CommunicationState::Online) {
            return reject("PROTOCOL_OFFLINE", "alarm request requires ONLINE communications");
        }
        std::string alarms;
        for (const auto& alarm : active_alarms_) {
            if (!alarms.empty()) alarms += ';';
            alarms += alarm;
        }
        return Result{true, "ALARM_REPORT", "active alarms reported", state_,
                      {{"alarm_count", std::to_string(active_alarms_.size())},
                       {"alarms", alarms}}};
    }
    if (command == "protocol_host_command") {
        if (communication_state_ != CommunicationState::Online) {
            return reject("PROTOCOL_OFFLINE", "remote command requires ONLINE communications");
        }
        if (control_mode_ != ControlMode::Remote) {
            return reject("PROTOCOL_NOT_REMOTE", "remote command requires REMOTE control mode");
        }
        const auto requested = params.find("command_name");
        if (requested == params.end()) {
            return reject("INVALID_REMOTE_COMMAND", "command_name is required");
        }
        std::map<std::string, std::string> forwarded = params;
        forwarded.erase("command_name");
        Result result;
        if (requested->second == "PROFILE") {
            result = load_profile(forwarded, correlation_id);
        } else if (requested->second == "START") {
            result = execute("start_run", {}, correlation_id);
        } else if (requested->second == "STOP") {
            result = execute("reset", {}, correlation_id);
        } else {
            return reject("INVALID_REMOTE_COMMAND", "unsupported simplified host command");
        }
        result.data["protocol_message"] = "REMOTE_COMMAND_ACK";
        result.data["command_name"] = requested->second;
        return result;
    }
    if (command == "emergency_stop") {
        return transition(State::EmergencyStop, "EMERGENCY_STOPPED",
                          "emergency stop engaged", correlation_id);
    }
    if (command == "clear_emergency_stop") {
        if (state_ != State::EmergencyStop) {
            return reject("INVALID_STATE", "emergency stop is not active");
        }
        interlock_open_ = false;
        return transition(State::Idle, "EMERGENCY_STOP_CLEARED",
                          "device returned to IDLE; homing required", correlation_id);
    }
    if (state_ == State::EmergencyStop) {
        return reject("SAFETY_INTERLOCK", "only status or clear_emergency_stop is allowed");
    }
    if (command == "power_on") {
        if (state_ != State::Boot) return reject("INVALID_STATE", "power_on requires BOOT");
        return transition(State::Idle, "SELF_TEST_PASSED", "power-on self-test passed", correlation_id);
    }
    if (command == "home") {
        if (state_ != State::Idle && state_ != State::Error) {
            return reject("INVALID_STATE", "home requires IDLE or ERROR");
        }
        if (interlock_open_) {
            return transition(State::EmergencyStop, "INTERLOCK_OPEN",
                              "motion blocked by safety interlock", correlation_id);
        }
        if (actuator_stuck_) {
            return transition(State::Error, "ACTUATOR_STUCK", "actuator failed to reach home", correlation_id);
        }
        const State from = state_;
        state_ = State::Homing;
        record(from, State::Homing, "HOMING_STARTED", correlation_id, "actuator homing started");
        return transition(State::Homed, "HOMING_COMPLETE", "actuator homing complete", correlation_id);
    }
    if (command == "calibrate") {
        if (state_ != State::Homed) return reject("INVALID_STATE", "calibrate requires HOMED");
        if (sensor_drift_) {
            return transition(State::Error, "CALIBRATION_FAILED",
                              "sensor drift exceeds calibration range", correlation_id);
        }
        state_ = State::Calibrating;
        record(State::Homed, State::Calibrating, "CALIBRATION_STARTED", correlation_id,
               "reference scan started");
        return transition(State::Ready, "CALIBRATION_COMPLETE", "calibration complete", correlation_id);
    }
    if (command == "load_profile") return load_profile(params, correlation_id);
    if (command == "start_run") {
        if (state_ != State::Ready && state_ != State::Complete) {
            return reject("INVALID_STATE", "run requires READY or COMPLETE");
        }
        if (!profile_) return reject("PROFILE_REQUIRED", "load a valid profile before run");
        if (interlock_open_) {
            return transition(State::EmergencyStop, "INTERLOCK_OPEN",
                              "run stopped by safety interlock", correlation_id);
        }
        const State from = state_;
        state_ = State::Running;
        record(from, State::Running, "RUN_STARTED", correlation_id, profile_->name);
        if (sensor_drift_) {
            return transition(State::Error, "SENSOR_DRIFT",
                              "run rejected because sensor drift exceeds limit", correlation_id);
        }
        ++run_count_;
        Result result = transition(State::Complete, "RUN_COMPLETE",
                                   "run completed", correlation_id);
        result.data["run_id"] = "R-" + std::to_string(run_count_);
        result.data["sample_count"] = std::to_string(profile_->sample_count);
        return result;
    }
    if (command == "reset") {
        if (state_ != State::Complete && state_ != State::Error && state_ != State::Warning) {
            return reject("INVALID_STATE", "reset requires COMPLETE, ERROR, or WARNING");
        }
        profile_.reset();
        return transition(State::Idle, "RESET_COMPLETE", "device reset; homing required", correlation_id);
    }
    return reject("UNKNOWN_COMMAND", "unsupported command");
}

}  // namespace edge





