#include "edge/protocol.hpp"

#include <chrono>
#include <iomanip>
#include <regex>
#include <sstream>

namespace edge {
namespace {

std::string escape_json(const std::string& value) {
    std::ostringstream out;
    for (const char ch : value) {
        switch (ch) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default: out << ch;
        }
    }
    return out.str();
}

std::string find_string(const std::string& input, const std::string& key) {
    const std::regex expression("\\\"" + key + "\\\"\\s*:\\s*\\\"([^\\\"]*)\\\"");
    std::smatch match;
    return std::regex_search(input, match, expression) ? match[1].str() : "";
}

std::string find_scalar(const std::string& input, const std::string& key) {
    const std::regex expression("\\\"" + key + "\\\"\\s*:\\s*([^,}]+)");
    std::smatch match;
    if (!std::regex_search(input, match, expression)) return "";
    std::string value = match[1].str();
    value.erase(0, value.find_first_not_of(" \t\r\n\""));
    const auto last = value.find_last_not_of(" \t\r\n\"");
    if (last != std::string::npos) value.erase(last + 1);
    return value;
}

std::string params_object(const std::string& line) {
    const auto key = line.find("\"params\"");
    if (key == std::string::npos) return "";
    const auto open = line.find('{', key);
    if (open == std::string::npos) return "";
    int depth = 0;
    bool quoted = false;
    for (std::size_t index = open; index < line.size(); ++index) {
        const char ch = line[index];
        if (ch == '"' && (index == 0 || line[index - 1] != '\\')) quoted = !quoted;
        if (quoted) continue;
        if (ch == '{') ++depth;
        if (ch == '}' && --depth == 0) return line.substr(open + 1, index - open - 1);
    }
    return "";
}

std::map<std::string, std::string> parse_params(const std::string& object) {
    std::map<std::string, std::string> params;
    const std::regex pair("\\\"([^\\\"]+)\\\"\\s*:\\s*(\\\"([^\\\"]*)\\\"|[-+0-9.eE]+|true|false|null)");
    for (auto it = std::sregex_iterator(object.begin(), object.end(), pair);
         it != std::sregex_iterator(); ++it) {
        std::string value = (*it)[2].str();
        if (value.size() >= 2 && value.front() == '"' && value.back() == '"') {
            value = value.substr(1, value.size() - 2);
        }
        params[(*it)[1].str()] = value;
    }
    return params;
}

std::int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
               std::chrono::system_clock::now().time_since_epoch())
        .count();
}

}  // namespace

std::uint32_t crc32(const std::string& value) {
    std::uint32_t crc = 0xFFFFFFFFu;
    for (const unsigned char byte : value) {
        crc ^= byte;
        for (int bit = 0; bit < 8; ++bit) {
            const std::uint32_t mask = 0u - (crc & 1u);
            crc = (crc >> 1u) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

std::string crc32_hex(const std::string& value) {
    std::ostringstream out;
    out << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << crc32(value);
    return out.str();
}

ParsedRequest parse_request(const std::string& line) {
    if (line.empty() || line.front() != '{' || line.back() != '}') {
        return {false, {}, "MALFORMED_JSON", "request must be a single JSON object"};
    }
    std::string object_body = line.substr(1, line.size() - 2);
    const auto last_content = object_body.find_last_not_of(" \t\r\n");
    const bool has_trailing_comma =
        last_content != std::string::npos && object_body[last_content] == ',';
    if (has_trailing_comma || (line != "{}" && line.find(':') == std::string::npos)) {
        return {false, {}, "MALFORMED_JSON", "request contains invalid object syntax"};
    }
    Request request;
    request.request_id = find_string(line, "request_id");
    request.command = find_string(line, "command");
    request.crc32 = find_string(line, "crc32");
    request.params = parse_params(params_object(line));
    if (request.request_id.empty()) {
        return {false, {}, "SCHEMA_ERROR", "request_id is required"};
    }
    if (request.command.empty()) {
        return {false, {}, "SCHEMA_ERROR", "command is required"};
    }
    if (!request.crc32.empty()) {
        const std::string expected = crc32_hex(request.request_id + "|" + request.command);
        if (request.crc32 != expected) {
            return {false, request, "CRC_ERROR", "request checksum mismatch"};
        }
    }
    return {true, request, "", ""};
}

std::string encode_response(const Result& result, const std::string& request_id,
                            std::uint64_t sequence) {
    std::ostringstream out;
    out << "{\"request_id\":\"" << escape_json(request_id) << "\","
        << "\"sequence\":" << sequence << ','
        << "\"timestamp_ms\":" << now_ms() << ','
        << "\"ok\":" << (result.ok ? "true" : "false") << ','
        << "\"code\":\"" << escape_json(result.code) << "\","
        << "\"message\":\"" << escape_json(result.message) << "\","
        << "\"state\":\"" << to_string(result.state) << "\","
        << "\"data\":{";
    bool first = true;
    for (const auto& [key, value] : result.data) {
        if (!first) out << ',';
        first = false;
        out << "\"" << escape_json(key) << "\":\"" << escape_json(value) << "\"";
    }
    out << "}}";
    return out.str();
}

std::string encode_event_log(const Event& event) {
    std::ostringstream out;
    out << "{\"sequence\":" << event.sequence
        << ",\"timestamp_ms\":" << event.timestamp_ms
        << ",\"correlation_id\":\"" << escape_json(event.correlation_id)
        << "\",\"event\":\"" << escape_json(event.event)
        << "\",\"from_state\":\"" << escape_json(event.from_state)
        << "\",\"to_state\":\"" << escape_json(event.to_state)
        << "\",\"detail\":\"" << escape_json(event.detail) << "\"}";
    return out.str();
}

}  // namespace edge


