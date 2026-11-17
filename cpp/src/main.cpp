#include "edge/bounded_queue.hpp"
#include "edge/protocol.hpp"
#include "edge/state_machine.hpp"

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cerrno>
#include <deque>
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

class SocketHandle {
public:
    explicit SocketHandle(socket_t socket) noexcept : socket_(socket) {}
    ~SocketHandle() { reset(); }
    SocketHandle(const SocketHandle&) = delete;
    SocketHandle& operator=(const SocketHandle&) = delete;
    SocketHandle(SocketHandle&& other) noexcept
        : socket_(std::exchange(other.socket_, invalid_socket)) {}
    SocketHandle& operator=(SocketHandle&& other) noexcept {
        if (this != &other) {
            reset();
            socket_ = std::exchange(other.socket_, invalid_socket);
        }
        return *this;
    }
    socket_t get() const noexcept { return socket_; }
    void reset() noexcept {
        if (socket_ != invalid_socket) close_socket(socket_);
        socket_ = invalid_socket;
    }
private:
    socket_t socket_;
};

void set_socket_timeout(socket_t socket, int option, int milliseconds) {
#ifdef _WIN32
    const DWORD timeout = static_cast<DWORD>(milliseconds);
    setsockopt(socket, SOL_SOCKET, option,
               reinterpret_cast<const char*>(&timeout), sizeof(timeout));
#else
    timeval timeout{};
    timeout.tv_sec = milliseconds / 1000;
    timeout.tv_usec = (milliseconds % 1000) * 1000;
    setsockopt(socket, SOL_SOCKET, option, &timeout, sizeof(timeout));
#endif
}

bool send_all(socket_t socket, const std::string& payload) {
    std::size_t sent = 0;
    while (sent < payload.size()) {
#ifdef MSG_NOSIGNAL
        constexpr int flags = MSG_NOSIGNAL;
#else
        constexpr int flags = 0;
#endif
        const auto count = send(socket, payload.data() + sent,
                               static_cast<int>(payload.size() - sent), flags);
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

std::string busy_response(bool expired = false) {
    return "{\"request_id\":\"server\",\"sequence\":1,\"timestamp_ms\":" +
           std::to_string(now_ms()) +
           (expired
                ? ",\"ok\":false,\"code\":\"QUEUE_TIMEOUT\",\"message\":\"queue wait expired\""
                : ",\"ok\":false,\"code\":\"SERVER_BUSY\",\"message\":\"connection queue is full\"") +
           ",\"state\":\"ERROR\",\"data\":{}}\n";
}

struct QueuedConnection {
    SocketHandle socket;
    std::chrono::steady_clock::time_point deadline;
};

struct SharedRuntime {
    explicit SharedRuntime(const std::string& log_path) : log(log_path, std::ios::app) {}

    std::mutex mutex;
    edge::DeviceRuntime device;
    std::ofstream log;
    std::uint64_t response_sequence{1};
    static constexpr std::size_t max_cached_responses = 1024;
    std::deque<std::string> response_order;
    std::map<std::string, std::pair<std::string, std::string>> response_cache;
};

std::string execute_line(SharedRuntime& runtime, const std::string& line) {
    const auto parsed = edge::parse_request(line);
    const std::string fingerprint = parsed.ok ? request_fingerprint(parsed.request) : "";
    std::lock_guard<std::mutex> lock(runtime.mutex);
    edge::Result result;
    const std::string request_id = parsed.request.request_id;
    bool cache_response = false;
    if (!parsed.ok) {
        result = {false, parsed.error_code, parsed.error_message, runtime.device.state(), {}};
    } else {
        const auto cached = runtime.response_cache.find(parsed.request.request_id);
        if (cached != runtime.response_cache.end()) {
            if (cached->second.first == fingerprint) return cached->second.second;
            result = {false, "REQUEST_ID_CONFLICT",
                      "request_id was already used with different content",
                      runtime.device.state(), {}};
        } else {
            cache_response = true;
            result = runtime.device.execute(parsed.request.command, parsed.request.params,
                                            parsed.request.request_id);
        }
    }

    const std::string response = edge::encode_response(
        result, request_id, runtime.response_sequence++);
    if (cache_response) {
        if (runtime.response_order.size() == SharedRuntime::max_cached_responses) {
            runtime.response_cache.erase(runtime.response_order.front());
            runtime.response_order.pop_front();
        }
        runtime.response_cache.emplace(request_id, std::make_pair(fingerprint, response));
        runtime.response_order.push_back(request_id);
    }
    if (!runtime.device.events().empty()) {
        for (const auto& event : runtime.device.events()) {
            runtime.log << edge::encode_event_log(event) << '\n';
        }
        runtime.log.flush();
        runtime.device.clear_events();
    }
    return response;
}

void handle_client(socket_t client, SharedRuntime& runtime) {
    constexpr std::size_t max_frame_bytes = 64 * 1024;
    constexpr auto frame_timeout = std::chrono::seconds(5);
    auto frame_started = std::chrono::steady_clock::now();
    set_socket_timeout(client, SO_RCVTIMEO, 250);
    std::string buffer;
    char chunk[4096];
    while (running) {
        if (std::chrono::steady_clock::now() - frame_started >= frame_timeout) return;
        const auto count = recv(client, chunk, sizeof(chunk), 0);
        if (count == 0) break;
        if (count < 0) {
#ifdef _WIN32
            const auto error = WSAGetLastError();
            if (error == WSAETIMEDOUT || error == WSAEWOULDBLOCK || error == WSAEINTR) continue;
#else
            if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) continue;
#endif
            return;
        }
        buffer.append(chunk, static_cast<std::size_t>(count));
        std::size_t newline = 0;
        while ((newline = buffer.find('\n')) != std::string::npos) {
            if (newline > max_frame_bytes) return;
            std::string line = buffer.substr(0, newline);
            buffer.erase(0, newline + 1);
            if (!line.empty() && line.back() == '\r') line.pop_back();
            const std::string response = execute_line(runtime, line);
            if (!send_all(client, response + "\n")) return;
            frame_started = std::chrono::steady_clock::now();
        }
        if (buffer.size() > max_frame_bytes) return;
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
    int queue_timeout_ms = 2000;
    try {
        port = integer_argument(argc, argv, "--port", 8765, 1, 65535);
        worker_count = integer_argument(argc, argv, "--workers", 4, 1, 64);
        queue_capacity = integer_argument(argc, argv, "--queue-capacity", 32, 1, 4096);
        queue_timeout_ms = integer_argument(argc, argv, "--queue-timeout-ms", 2000, 1, 60000);
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
    struct WinsockSession { ~WinsockSession() { WSACleanup(); } } winsock_session;
#endif

    SocketHandle server_handle(socket(AF_INET, SOCK_STREAM, IPPROTO_TCP));
    const socket_t server = server_handle.get();
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
        return 2;
    }

    edge::BoundedQueue<QueuedConnection> queue(static_cast<std::size_t>(queue_capacity));
    SharedRuntime runtime(log_path);
    std::vector<std::thread> workers;
    workers.reserve(static_cast<std::size_t>(worker_count));
    try {
      for (int index = 0; index < worker_count; ++index) {
        workers.emplace_back([&queue, &runtime] {
            while (const auto client = queue.pop()) {
                try {
                    if (!running) break;
                    if (std::chrono::steady_clock::now() >= client->deadline) {
                        send_all(client->socket.get(), busy_response(true));
                        continue;
                    }
                    handle_client(client->socket.get(), runtime);
                } catch (const std::exception& error) {
                    std::cerr << "connection handler failed: " << error.what() << '\n';
                }
            }
        });
      }
    } catch (const std::system_error& error) {
        queue.stop();
        for (auto& worker : workers) worker.join();
        std::cerr << "worker startup failed: " << error.what() << '\n';
        return 2;
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
        QueuedConnection client{
            SocketHandle(accept(server, reinterpret_cast<sockaddr*>(&client_address), &length)),
            std::chrono::steady_clock::now() + std::chrono::milliseconds(queue_timeout_ms)
        };
        if (client.socket.get() == invalid_socket) continue;
        set_socket_timeout(client.socket.get(), SO_SNDTIMEO, 250);
        if (!queue.try_push(std::move(client))) {
            send_all(client.socket.get(), busy_response());
        }
    }

    server_handle.reset();
    queue.stop();
    for (auto& worker : workers) worker.join();
    return 0;
}
