# Known Limitations

1. The simulator models deterministic software states, not physical device behavior.
2. Operations complete synchronously; there is no real-time motion loop.
3. The TCP server processes one client connection at a time.
4. The minimal C++ JSON parser accepts the documented flat request schema only.
5. CRC32 covers request ID and command, not a canonical serialization of all parameters.
6. There is no durable checkpoint or restart recovery in the MVP.
7. The 50-cycle repeatability test is not a two-hour endurance qualification.
8. There is no GUI or physical hardware-in-the-loop in the completed MVP.
9. C++ coverage is not yet collected in the default Windows build.
10. The control layer is a project-specific JSON Lines protocol, not an implementation of an industry standard.
11. The completed-response cache is in-memory and unbounded; a production service would add expiry, persistence and capacity control.
12. Concurrent clients are accepted through the socket backlog but processed sequentially; no real-time or throughput guarantee is claimed.

These limitations are intentional scope controls. They prevent a portfolio demonstration from being misrepresented as production device software or hardware qualification.



