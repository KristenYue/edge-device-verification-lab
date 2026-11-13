#include "edge/protocol.hpp"
#include "edge/state_machine.hpp"
#include "edge/bounded_queue.hpp"

#include <cstdlib>
#include <iostream>
#include <map>
#include <string>

namespace {

int failures = 0;

void check(bool condition, const std::string& label) {
    if (!condition) {
        ++failures;
        std::cerr << "FAIL: " << label << '\n';
    }
}

edge::Result run(edge::DeviceRuntime& device, const std::string& command,
                      std::map<std::string, std::string> params = {}) {
    return device.execute(command, params, "test-correlation");
}

void test_happy_path() {
    edge::DeviceRuntime device;
    check(device.state() == edge::State::Boot, "starts in BOOT");
    check(run(device, "power_on").ok, "power_on succeeds");
    check(run(device, "home").ok, "home succeeds");
    check(run(device, "calibrate").ok, "calibrate succeeds");
    check(run(device, "load_profile", {{"name", "batch-01"}, {"sample_count", "128"}}).ok,
          "valid profile succeeds");
    const auto result = run(device, "start_run");
    check(result.ok && result.state == edge::State::Complete, "run completes");
    check(device.run_count() == 1, "run count increments");
    check(device.events().size() >= 7, "events are retained");
}

void test_state_guards() {
    edge::DeviceRuntime device;
    check(run(device, "home").code == "INVALID_STATE", "home before power rejected");
    check(run(device, "start_run").code == "INVALID_STATE",
          "run in BOOT rejected");
    run(device, "power_on");
    check(run(device, "calibrate").code == "INVALID_STATE",
          "calibrate before home rejected");
    run(device, "home");
    run(device, "calibrate");
    check(run(device, "start_run").code == "PROFILE_REQUIRED",
          "run without profile rejected");
}

void test_profile_boundaries() {
    edge::DeviceRuntime device;
    run(device, "power_on");
    run(device, "home");
    run(device, "calibrate");
    check(!run(device, "load_profile", {{"sample_count", "9"}}).ok,
          "too few samples rejected");
    check(!run(device, "load_profile", {{"sample_count", "100001"}}).ok,
          "too many samples rejected");
    check(!run(device, "load_profile", {{"noise_sigma", "1.1"}}).ok,
          "excess noise rejected");
    check(!run(device, "load_profile", {{"drift_limit", "0"}}).ok,
          "zero drift limit rejected");
    check(!run(device, "load_profile", {{"sample_count", "abc"}}).ok,
          "non-numeric sample count rejected");
}

void test_faults_and_safety() {
    edge::DeviceRuntime device;
    run(device, "power_on");
    run(device, "inject_fault", {{"type", "interlock_open"}});
    const auto blocked = run(device, "home");
    check(!blocked.ok || blocked.state == edge::State::EmergencyStop,
          "open interlock blocks motion");
    check(run(device, "power_on").code == "SAFETY_INTERLOCK",
          "commands blocked during emergency stop");
    check(run(device, "clear_emergency_stop").ok, "emergency stop can be cleared");
    run(device, "inject_fault", {{"type", "actuator_stuck"}});
    check(run(device, "home").code == "ACTUATOR_STUCK", "actuator stuck is diagnosed");
    run(device, "inject_fault", {{"type", "clear"}});
    check(run(device, "home").ok, "homing succeeds after fault clear");
}

void test_protocol() {
    const std::string checksum = edge::crc32_hex("r-1|status");
    const auto valid = edge::parse_request(
        "{\"request_id\":\"r-1\",\"command\":\"status\",\"params\":{},\"crc32\":\"" +
        checksum + "\"}");
    check(valid.ok, "valid request parses");
    const auto bad_crc = edge::parse_request(
        "{\"request_id\":\"r-1\",\"command\":\"status\",\"crc32\":\"00000000\"}");
    check(!bad_crc.ok && bad_crc.error_code == "CRC_ERROR", "bad CRC rejected");
    check(!edge::parse_request("not json").ok, "malformed JSON rejected");
    check(edge::parse_request("{garbage}").error_code == "MALFORMED_JSON",
          "brace-wrapped garbage rejected as malformed");
    check(edge::parse_request("{\"request_id\":\"r\",}").error_code == "MALFORMED_JSON",
          "trailing comma rejected as malformed");
    check(!edge::parse_request("{\"command\":\"status\"}").ok,
          "missing request id rejected");
}

void test_simplified_protocol_control() {
    edge::DeviceRuntime device;
    check(device.communication_state() == edge::CommunicationState::Offline,
          "control protocol starts offline");
    check(device.control_mode() == edge::ControlMode::Local,
          "control protocol starts local");
    check(run(device, "protocol_set_remote").code == "PROTOCOL_OFFLINE",
          "remote rejected while offline");
    check(run(device, "protocol_establish_communications").code == "COMMUNICATIONS_ESTABLISHED",
          "communications established");
    check(run(device, "protocol_host_command", {{"command_name", "START"}}).code ==
              "PROTOCOL_NOT_REMOTE",
          "host command rejected in local mode");
    check(run(device, "protocol_set_remote").code == "REMOTE_MODE_ACK",
          "remote control selected");
    const auto variables = run(device, "protocol_get_variables");
    check(variables.ok && variables.data.at("CONTROL_MODE") == "REMOTE",
          "control protocol variables expose control mode");
    run(device, "inject_fault", {{"type", "interlock_open"}});
    const auto alarms = run(device, "protocol_get_alarms");
    check(alarms.data.at("alarm_count") == "1", "control protocol alarm is reported");
    run(device, "inject_fault", {{"type", "clear"}});
    check(run(device, "protocol_get_alarms").data.at("alarm_count") == "0",
          "control protocol alarm can be cleared");
}

void test_bounded_queue() {
    edge::BoundedQueue<int> queue(2);
    check(queue.capacity() == 2, "queue exposes configured capacity");
    check(queue.try_push(10), "first queue item accepted");
    check(queue.try_push(20), "second queue item accepted");
    check(!queue.try_push(30), "queue rejects work above capacity");
    check(queue.size() == 2, "queue size is bounded");
    check(queue.pop() == 10, "queue preserves FIFO order");
    check(queue.pop() == 20, "queue returns second item");
    queue.stop();
    check(!queue.try_push(40), "stopped queue rejects new work");
    check(!queue.pop().has_value(), "stopped empty queue wakes consumers");
}

}  // namespace

int main() {
    test_happy_path();
    test_state_guards();
    test_profile_boundaries();
    test_faults_and_safety();
    test_protocol();
    test_simplified_protocol_control();
    test_bounded_queue();
    if (failures == 0) {
        std::cout << "All edge device core tests passed\n";
        return EXIT_SUCCESS;
    }
    std::cerr << failures << " test(s) failed\n";
    return EXIT_FAILURE;
}




