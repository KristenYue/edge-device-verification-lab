#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace edge {

enum class State {
    Boot,
    Idle,
    Homing,
    Homed,
    Calibrating,
    Ready,
    Running,
    Complete,
    Warning,
    Error,
    EmergencyStop,
    Recovering,
};

enum class CommunicationState { Offline, Online };
enum class ControlMode { Local, Remote };

struct TaskProfile {
    std::string name{"default"};
    int sample_count{100};
    double noise_sigma{0.02};
    double drift_limit{0.20};
};

struct Result {
    bool ok{false};
    std::string code;
    std::string message;
    State state{State::Boot};
    std::map<std::string, std::string> data;
};

struct Event {
    std::uint64_t sequence{0};
    std::int64_t timestamp_ms{0};
    std::string correlation_id;
    std::string event;
    std::string from_state;
    std::string to_state;
    std::string detail;
};

class DeviceRuntime {
public:
    DeviceRuntime();

    Result execute(const std::string& command,
                   const std::map<std::string, std::string>& params,
                   const std::string& correlation_id);
    State state() const noexcept;
    std::string state_name() const;
    const std::vector<Event>& events() const noexcept;
    void clear_events() noexcept { events_.clear(); }
    std::uint64_t run_count() const noexcept;
    bool profile_loaded() const noexcept;
    CommunicationState communication_state() const noexcept;
    ControlMode control_mode() const noexcept;

private:
    State state_{State::Boot};
    std::optional<TaskProfile> profile_;
    std::vector<Event> events_;
    std::uint64_t next_sequence_{1};
    std::uint64_t run_count_{0};
    bool interlock_open_{false};
    bool actuator_stuck_{false};
    bool sensor_drift_{false};
    int response_delay_ms_{0};
    CommunicationState communication_state_{CommunicationState::Offline};
    ControlMode control_mode_{ControlMode::Local};
    std::set<std::string> active_alarms_;

    Result transition(State target, const std::string& code, const std::string& message,
                      const std::string& correlation_id);
    Result reject(const std::string& code, const std::string& message) const;
    void record(State from, State to, const std::string& event,
                const std::string& correlation_id, const std::string& detail);
    Result load_profile(const std::map<std::string, std::string>& params,
                       const std::string& correlation_id);
    Result inject_fault(const std::map<std::string, std::string>& params,
                        const std::string& correlation_id);
};

std::string to_string(State state);
std::string to_string(CommunicationState state);
std::string to_string(ControlMode mode);

}  // namespace edge




