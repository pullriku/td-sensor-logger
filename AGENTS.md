# AGENTS.md

## Purpose

This repository logs temperature, humidity, and pressure data from a Tokyo Devices sensor via `td-usb`, then writes buffered samples to `Parquet` files under `data/`.

The main Rust binary is `td-sensor-logger`. A small Python utility in `sensor-plotter/` renders saved parquet files to PNG.

## Repository Layout

- `src/main.rs`: CLI entrypoint. Parses `model_name`, `--interval`, and `--flush-count`.
- `src/lib.rs`: Core logger loop, signal handling, sensor reads, buffering, and parquet writing.
- `start.sh`: Starts the release binary in the background and writes `logger.pid` / `logger.log`.
- `start_test.sh`: Same as `start.sh`, but with a short sampling interval for quick checks.
- `stop.sh`: Sends `SIGINT` to the running logger so it flushes before exit.
- `flush.sh`: Sends `SIGUSR1` to force a buffer flush.
- `sensor-plotter/main.py`: Plotting utility for generated parquet files.
- `README.md`: User-facing usage documentation. Keep it aligned with behavior changes.

## Working Rules

- Prefer minimal, targeted changes. Preserve the current CLI and script workflow unless the task explicitly requires changing it.
- If behavior changes, update `README.md` and any affected helper scripts in the same pass.
- Do not assume sensor hardware is available. Distinguish clearly between unit-tested behavior and hardware-dependent behavior.
- Treat `data/`, `logger.log`, and `logger.pid` as runtime artifacts. Do not commit generated files unless the user explicitly asks.

## Common Commands

Build and test from the repository root:

```bash
cargo build --release
cargo test
```

Run locally in the foreground:

```bash
cargo run --release -- tdsn7200 --interval 60 --flush-count 10000
```

Background operation:

```bash
./start.sh
./start_test.sh
./flush.sh
./stop.sh
```

If `just` is installed:

```bash
just start
just flush
just stop
just plot
```

Plot saved data:

```bash
cd sensor-plotter
uv sync
uv run python main.py
```

## Verification Expectations

- For Rust code changes, run `cargo test`.
- If CLI behavior, scripts, or docs changed, also verify the relevant command examples still match reality.
- If work touches actual sensor reads or signal-driven flushing, mention whether the behavior was only reasoned from code or exercised against a real running process.
- If changes affect parquet output or plotting, verify both the Rust producer side and the `sensor-plotter/` consumer side when feasible.

## Implementation Notes

- Sensor reads are performed by spawning `td-usb <model_name> get`.
- The expected stdout format is three comma-separated numeric values in this order:
  `temperature_c,humidity_pct,pressure_hpa`
- Samples are buffered in memory and flushed to parquet either when `flush_count` is reached, when `SIGUSR1` is received, or during shutdown on `SIGINT` / `SIGTERM`.
- Parquet files are written with Snappy compression into `data/` using local time in the filename.
- The writer runs on a dedicated thread fed by a bounded sync channel. Preserve shutdown and flush ordering when changing concurrency behavior.

## When Editing

- Keep tests close to the logic they cover; existing unit tests live in `src/lib.rs`.
- Prefer adding or updating unit tests for queueing, flush triggering, and shutdown semantics before changing concurrency-sensitive code.
- Be careful with timing logic in `wait_for_event`; avoid changes that introduce busy waiting or missed signal handling.
- Keep shell scripts POSIX/Bash-simple. They are intended for local operation, not a process supervisor.
