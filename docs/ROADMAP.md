# Engineering Roadmap

The repository is already a runnable C++17/Python validation baseline. The next work is
ordered by evidence value for system-software, developer-tooling and verification roles.

## P1: Linux concurrency and process behavior - implemented locally

- Replaced the sequential accept loop with a configurable bounded worker pool.
- Added queue-full `SERVER_BUSY`, synchronized runtime ownership and signal-aware shutdown.
- Added concurrent duplicate-command, queue saturation and POSIX shutdown tests.
- Passed the Ubuntu ASan/UBSan workflow in GitHub Actions run `43424447863`.

Exit evidence:

- no race or memory-safety failure in the defined test suite;
- documented maximum queue size and rejection behavior;
- deterministic concurrent-request tests in CI.

## P2: Smart-shelf protocol adapter - implemented locally

- Added versioned v1 telemetry fixtures based on the public Smart Shelf contract.
- Added two-device validation, ordering, duplicate/conflict handling and command authorization.
- Kept MQTT/AWS execution outside the adapter; the default path is local and key-free.

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
