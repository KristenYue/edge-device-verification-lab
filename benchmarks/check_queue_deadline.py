"""Smoke check for a server started with one worker and a 100 ms queue deadline."""

import argparse
import json
import socket
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18766)
    args = parser.parse_args()
    address = ("127.0.0.1", args.port)
    with socket.create_connection(address, timeout=3) as held:
        # The incomplete frame keeps the single worker occupied.
        held.sendall(b"{")
        time.sleep(0.1)
        with socket.create_connection(address, timeout=3) as queued:
            queued.sendall(b'{"command":"status","request_id":"queued"}\n')
            time.sleep(0.25)
            held.shutdown(socket.SHUT_WR)
            with queued.makefile("rb") as response:
                result = json.loads(response.readline())
    assert result["code"] == "QUEUE_TIMEOUT", result
    print(json.dumps(result))


if __name__ == "__main__":
    main()
