#include "edge/protocol.hpp"
#include "edge/state_machine.hpp"

#include <atomic>
#include <csignal>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
using socket_t = SOCKET;
constexpr socket_t invalid_socket = INVALID_SOCKET;
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
using socket_t = int;
constexpr socket_t invalid_socket = -1;
#endif

namespace {

std::atomic<bool> running{true};

void on_signal(int) { running = false; }

void close_socket(socket_t socket) {
#ifdef _WIN32
    closesocket(socket);
#else
    close(socket);
#endif
}

bool send_all(socket_t socket, const std::string& payload) {
    std::size_t sent = 0;
    while (sent < payload.size()) {
        const int count = send(socket, payload.data() + sent,
                               static_cast<int>(payload.size() - sent), 0);
        if (count <= 0) return false;
        sent += static_cast<std::size_t>(count);
    }
    return true;
}

int parse_port(int argc, char** argv) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (std::string(argv[i]) == "--port") return std::stoi(argv[i + 1]);
    }
    return 8765;
}

std::string parse_log_path(int argc, char** argv) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (std::string(argv[i]) == "--log") return argv[i + 1];
    }
    return "device-events.jsonl";
}

std::string request_fingerprint(const edge::Request& request) {
    std::ostringstream out;
    out << request.command;
    for (const auto& [key, value] : request.params) out << '|' << key << '=' << value;
    return out.str();
}

}  // namespace

int main(int argc, char** argv) {
    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);
    const int port = parse_port(argc, argv);
    const std::string log_path = parse_log_path(argc, argv);

#ifdef _WIN32
    WSADATA data{};
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
        std::cerr << "WSAStartup failed\n";
        return 2;
    }
#endif

    socket_t server = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (server == invalid_socket) {
        std::cerr << "failed to create socket\n";
        return 2;
    }
    int reuse = 1;
    setsockopt(server, SOL_SOCKET, SO_REUSEADDR,
               reinterpret_cast<const char*>(&reuse), sizeof(reuse));
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = htons(static_cast<unsigned short>(port));
    if (bind(server, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0 ||
        listen(server, 8) != 0) {
        std::cerr << "failed to bind/listen on 127.0.0.1:" << port << "\n";
        close_socket(server);
        return 2;
    }

    std::ofstream log(log_path, std::ios::app);
    edge::DeviceRuntime device;
    std::uint64_t response_sequence = 1;
    std::size_t logged_events = 0;
    std::map<std::string, std::pair<std::string, std::string>> response_cache;
    std::cout << "READY 127.0.0.1:" << port << std::endl;

    while (running) {
        sockaddr_in client_address{};
#ifdef _WIN32
        int length = sizeof(client_address);
#else
        socklen_t length = sizeof(client_address);
#endif
        socket_t client = accept(server, reinterpret_cast<sockaddr*>(&client_address), &length);
        if (client == invalid_socket) {
            if (running) std::cerr << "accept failed\n";
            continue;
        }
        std::string buffer;
        char chunk[4096];
        while (running) {
            const int count = recv(client, chunk, sizeof(chunk), 0);
            if (count <= 0) break;
            buffer.append(chunk, static_cast<std::size_t>(count));
            std::size_t newline = 0;
            while ((newline = buffer.find('\n')) != std::string::npos) {
                std::string line = buffer.substr(0, newline);
                buffer.erase(0, newline + 1);
                if (!line.empty() && line.back() == '\r') line.pop_back();
                const auto parsed = edge::parse_request(line);
                edge::Result result;
                std::string request_id = parsed.request.request_id;
                if (!parsed.ok) {
                    result = {false, parsed.error_code, parsed.error_message,
                              device.state(), {}};
                } else {
                    const std::string fingerprint = request_fingerprint(parsed.request);
                    const auto cached = response_cache.find(parsed.request.request_id);
                    if (cached != response_cache.end()) {
                        if (cached->second.first == fingerprint) {
                            if (!send_all(client, cached->second.second + "\n")) break;
                            continue;
                        }
                        result = {false, "REQUEST_ID_CONFLICT",
                                  "request_id was already used with different content",
                                  device.state(), {}};
                    } else {
                        result = device.execute(parsed.request.command, parsed.request.params,
                                                   parsed.request.request_id);
                    }
                }
                const std::string response = edge::encode_response(
                    result, request_id, response_sequence++);
                if (parsed.ok && response_cache.find(parsed.request.request_id) == response_cache.end()) {
                    response_cache[parsed.request.request_id] = {
                        request_fingerprint(parsed.request), response};
                }
                if (!send_all(client, response + "\n")) break;
                while (logged_events < device.events().size()) {
                    log << edge::encode_event_log(device.events()[logged_events++]) << '\n';
                    log.flush();
                }
            }
        }
        close_socket(client);
    }

    close_socket(server);
#ifdef _WIN32
    WSACleanup();
#endif
    return 0;
}



