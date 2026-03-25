from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import polars as pl


JST = ZoneInfo("Asia/Tokyo")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot td-sensor-logger parquet files into a PNG graph."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("../data"),
        help="Directory containing parquet files written by td-sensor-logger.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("plots/sensor-history.png"),
        help="Path to the output PNG file.",
    )
    return parser.parse_args()


def load_data(data_dir: Path) -> pl.DataFrame:
    parquet_files = sorted(data_dir.glob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"No parquet files found in {data_dir}")

    return pl.read_parquet(parquet_files).sort("ts_ms")


def plot_data(df: pl.DataFrame, output_path: Path) -> None:
    timestamps = [
        datetime.fromtimestamp(ts_ms / 1000, tz=JST) for ts_ms in df["ts_ms"].to_list()
    ]
    temperature = df["temperature_c"].to_list()
    humidity = df["humidity_pct"].to_list()
    pressure = df["pressure_hpa"].to_list()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True, constrained_layout=True)

    axes[0].plot(timestamps, temperature, color="#c2410c", linewidth=2)
    axes[0].set_ylabel("Temp (C)")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(timestamps, humidity, color="#0369a1", linewidth=2)
    axes[1].set_ylabel("Humidity (%)")
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(timestamps, pressure, color="#3f6212", linewidth=2)
    axes[2].set_ylabel("Pressure (hPa)")
    axes[2].set_xlabel("Timestamp")
    axes[2].grid(True, alpha=0.3)

    fig.suptitle("TD Sensor Logger History")
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    df = load_data(args.data_dir)
    plot_data(df, args.output)
    print(f"Saved plot to {args.output}")


if __name__ == "__main__":
    main()
