#include "edge/bounded_queue.hpp"
#include "edge/protocol.hpp"
#include "edge/state_machine.hpp"

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
using socket_t = SOCKET;
constexpr socket_t invalid_socket = INVALID_SOCKET;
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/time.h>
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

void set_receive_timeout(socket_t socket, int milliseconds) {
#ifdef _WIN32
    const DWORD timeout = static_cast<DWORD>(milliseconds);
    setsockopt(socket, SOL_SOCKET, SO_RCVTIMEO,
               reinterpret_cast<const char*>(&timeout), sizeof(timeout));
#else
    timeval timeout{};
    timeout.tv_sec = milliseconds / 1000;
    timeout.tv_usec = (milliseconds % 1000) * 1000;
    setsockopt(socket, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
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

int integer_argument(int argc, char** argv, const std::string& name, int fallback,
                     int minimum, int maximum) {
    for (int index = 1; index + 1 < argc; ++index) {
        if (std::string(argv[index]) != name) continue;
        const int value = std::stoi(argv[index + 1]);
        if (value < minimum || value > maximum) {
            throw std::invalid_argument(name + " must be between " +
                                        std::to_string(minimum) + " and " +
                                        std::to_string(maximum));
        }
        return value;
    }
    return fallback;
}

std::string parse_log_path(int argc, char** argv) {
    for (int index = 1; index + 1 < argc; ++index) {
        if (std::string(argv[index]) == "--log") return argv[index + 1];
    }
    return "device-events.jsonl";
}

std::string request_fingerprint(const edge::Request& request) {
    std::ostringstream out;
    out << request.command;
    for (const auto& [key, value] : request.params) out << '|' << key << '=' << value;
    return out.str();
}

std::int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
               std::chrono::system_clock::now().time_since_epoch())
        .count();
}

std::string busy_response() {
    return "{\"request_id\":\"server\",\"sequence\":1,\"timestamp_ms\":" +
           std::to_string(now_ms()) +
           ",\"ok\":false,\"code\":\"SERVER_BUSY\","
           "\"message\":\"connection queue is full\",\"state\":\"ERROR\",\"data\":{}}\n";
}

struct SharedRuntime {
    explicit SharedRuntime(const std::string& log_path) : log(log_path, std::ios::app) {}

    std::mutex mutex;
    edge::DeviceRuntime device;
    std::ofstream log;
    std::uint64_t response_sequence{1};
    std::size_t logged_events{0};
    std::map<std::string, std::pair<std::string, std::string>> response_cache;
};

std::string execute_line(SharedRuntime& runtime, const std::string& line) {
    const auto parsed = edge::parse_request(line);
    std::lock_guard<std::mutex> lock(runtime.mutex);
    edge::Result result;
    const std::string request_id = parsed.request.request_id;
    if (!parsed.ok) {
        result = {false, parsed.error_code, parsed.error_message, runtime.device.state(), {}};
    } else {
        const std::string fingerprint = request_fingerprint(parsed.request);
        const auto cached = runtime.response_cache.find(parsed.request.request_id);
        if (cached != runtime.response_cache.end()) {
            if (cached->second.first == fingerprint) return cached->second.second;
            result = {false, "REQUEST_ID_CONFLICT",
                      "request_id was already used with different content",
                      runtime.device.state(), {}};
        } else {
            result = runtime.device.execute(parsed.request.command, parsed.request.params,
                                            parsed.request.request_id);
        }
    }

    const std::string response = edge::encode_response(
        result, request_id, runtime.response_sequence++);
    if (parsed.ok &&
        runtime.response_cache.find(parsed.request.request_id) == runtime.response_cache.end()) {
        runtime.response_cache[parsed.request.request_id] = {
            request_fingerprint(parsed.request), response};
    }
    while (runtime.logged_events < runtime.device.events().size()) {
        runtime.log << edge::encode_event_log(
                           runtime.device.events()[runtime.logged_events++])
                    << '\n';
        runtime.log.flush();
    }
    return response;
}

void handle_client(socket_t client, SharedRuntime& runtime) {
    set_receive_timeout(client, 250);
    std::string buffer;
    char chunk[4096];
    while (running) {
        const int count = recv(client, chunk, sizeof(chunk), 0);
        if (count == 0) break;
        if (count < 0) continue;
        buffer.append(chunk, static_cast<std::size_t>(count));
        std::size_t newline = 0;
        while ((newline = buffer.find('\n')) != std::string::npos) {
            std::string line = buffer.substr(0, newline);
            buffer.erase(0, newline + 1);
            if (!line.empty() && line.back() == '\r') line.pop_back();
            const std::string response = execute_line(runtime, line);
            if (!send_all(client, response + "\n")) return;
        }
    }
}

bool wait_for_connection(socket_t server) {
    fd_set read_set;
    FD_ZERO(&read_set);
    FD_SET(server, &read_set);
    timeval timeout{};
    timeout.tv_usec = 200000;
    return select(static_cast<int>(server) + 1, &read_set, nullptr, nullptr, &timeout) > 0;
}

}  // namespace

int main(int argc, char** argv) {
    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);

    int port = 8765;
    int worker_count = 4;
    int queue_capacity = 32;
    try {
        port = integer_argument(argc, argv, "--port", 8765, 1, 65535);
        worker_count = integer_argument(argc, argv, "--workers", 4, 1, 64);
        queue_capacity = integer_argument(argc, argv, "--queue-capacity", 32, 1, 4096);
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
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
        listen(server, queue_capacity + worker_count) != 0) {
        std::cerr << "failed to bind/listen on 127.0.0.1:" << port << "\n";
        close_socket(server);
        return 2;
    }

    edge::BoundedQueue<socket_t> queue(static_cast<std::size_t>(queue_capacity));
    SharedRuntime runtime(log_path);
    std::vector<std::thread> workers;
    workers.reserve(static_cast<std::size_t>(worker_count));
    for (int index = 0; index < worker_count; ++index) {
        workers.emplace_back([&queue, &runtime] {
            while (const auto client = queue.pop()) {
                handle_client(*client, runtime);
                close_socket(*client);
            }
        });
    }

    std::cout << "READY 127.0.0.1:" << port << " workers=" << worker_count
              << " queue_capacity=" << queue_capacity << std::endl;

    while (running) {
        if (!wait_for_connection(server)) continue;
        sockaddr_in client_address{};
#ifdef _WIN32
        int length = sizeof(client_address);
#else
        socklen_t length = sizeof(client_address);
#endif
        socket_t client = accept(server, reinterpret_cast<sockaddr*>(&client_address), &length);
        if (client == invalid_socket) continue;
        if (!queue.try_push(client)) {
            send_all(client, busy_response());
            close_socket(client);
        }
    }

    close_socket(server);
    queue.stop();
    for (auto& worker : workers) worker.join();
#ifdef _WIN32
    WSACleanup();
#endif
    return 0;
}
