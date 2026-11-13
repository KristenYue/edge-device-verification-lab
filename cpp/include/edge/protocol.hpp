#pragma once

#include "edge/state_machine.hpp"

#include <cstdint>
#include <map>
#include <string>

namespace edge {

struct Request {
    std::string request_id;
    std::string command;
    std::map<std::string, std::string> params;
    std::string crc32;
};

struct ParsedRequest {
    bool ok{false};
    Request request;
    std::string error_code;
    std::string error_message;
};

ParsedRequest parse_request(const std::string& line);
std::string encode_response(const Result& result, const std::string& request_id,
                            std::uint64_t sequence);
std::string encode_event_log(const Event& event);
std::uint32_t crc32(const std::string& value);
std::string crc32_hex(const std::string& value);

}  // namespace edge


