# Learning and Interview Guide

## What you need to understand

You do not need to memorize every line. You should be able to explain these seven ideas:

1. Why device commands are guarded by state rather than accepted at any time.
2. Why an open interlock must fail closed and enter E_STOP.
3. How request ID, event sequence and timestamp reconstruct a failure timeline.
4. Why transport timeout differs from an explicit device rejection.
5. How boundary tests protect TaskProfile parameters before device execution.
6. Why the Python tests act as an external user of the C++ device rather than calling internal methods.
7. Which limitations stop this project from being described as a real edge-device tool.

## Seven-day learning path

| Day | Learn | Demonstrate |
|---|---|---|
| 1 | Read product requirements and draw the state machine | Explain one normal and one illegal transition |
| 2 | Read `state_machine.hpp/.cpp` and basic C++ class syntax | Change a validation boundary and update its test |
| 3 | Learn CMake targets and run CTest | Build from an empty `build` directory |
| 4 | Read the protocol and Python client | Explain request ID, CRC and timeout classification |
| 5 | Read pytest fixtures and parameterized tests | Add one negative TaskProfile case |
| 6 | Run three injected faults and inspect JSONL | Reconstruct the root cause from the event sequence |
| 7 | Practice the three-minute demo and evidence boundary | State what the project proves and does not prove |

## Interview summary

“I built a locally reproducible test bench for a simplified edge device tool. The device under test is a C++ state machine with safety interlocks, TaskProfile validation, a TCP command protocol and structured event traces. A separate Python/pytest harness verifies normal, boundary, negative, recovery and repeated-run behavior through the public interface. I deliberately kept the physics synthetic and documented that boundary, because the purpose is to demonstrate device software validation and fault diagnosis rather than claim experience with a proprietary production tool.”

## Likely follow-up questions

- Why C++ for the simulator and Python for validation?
- How would you add asynchronous motion and cancellation?
- What happens if a timeout occurs after the device executed a command?
- How would idempotency and durable checkpoints change the design?
- What would need to change before exposing the service beyond loopback?
- How would you test real serial hardware or a motion controller?
- Which tests are unit, integration, system and recovery tests?



