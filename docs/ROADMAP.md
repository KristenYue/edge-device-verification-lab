# Engineering Roadmap

The repository is already a runnable C++17/Python validation baseline. The next work is
ordered by evidence value for system-software, developer-tooling and verification roles.

## P1: Linux concurrency and process behavior

- Replace the sequential accept loop with a bounded worker pool.
- Add clean shutdown, worker ownership and backpressure behavior.
- Add tests for concurrent state-changing requests and shutdown during active work.
- Run ASan/UBSan on Ubuntu and retain the workflow evidence.

Exit evidence:

- no race or memory-safety failure in the defined test suite;
- documented maximum queue size and rejection behavior;
- deterministic concurrent-request tests in CI.

## P2: Smart-shelf protocol adapter

- Add a simulator profile using the public telemetry and command contract from the
  `smart-supermarket-shelf` project.
- Model two device identities, telemetry sequence numbers, duplicate messages and
  out-of-order delivery.
- Keep MQTT/AWS integration optional; the default test path remains local and key-free.

Exit evidence:

- contract tests share versioned JSON fixtures with the smart-shelf repository;
- cross-device isolation and command authorization tests pass;
- README clearly separates simulated protocol evidence from physical-hardware evidence.

## P3: Performance and endurance evidence

- Add a deterministic load driver and record throughput, P50/P95 latency and peak RSS.
- Add a fixed-duration endurance scenario with explicit machine and build metadata.
- Publish raw JSON results and a small Markdown summary generated from the same data.

Exit evidence:

- one-command reproducibility;
- no manually typed performance claims;
- every resume metric points to a machine-readable report.

## P4: Optional Linux systems extension

- Add a Unix-domain-socket transport on Linux.
- Document GDB, core-dump and `strace` diagnosis for one injected failure.
- Consider a QEMU-only virtual sensor driver as a separate, clearly scoped module.

This phase must not be described as device-driver or hardware bring-up experience until
the implementation, build instructions and tests exist.
