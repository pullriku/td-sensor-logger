from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.ticker import FixedLocator, FuncFormatter


JST = ZoneInfo("Asia/Tokyo")
SAMPLING_INTERVAL_SEC = 10 * 60
TICK_HOURS = np.array([0.5, 1, 2, 3, 6, 12, 24, 48, 72, 168], dtype=float)
SERIES_SPECS = [
    ("temperature_c", "Temperature", "tab:red"),
    ("humidity_pct", "Humidity", "tab:blue"),
    ("pressure_hpa", "Pressure", "tab:green"),
]


def parse_datetime_arg(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Datetime must be ISO 8601 like 2026-06-01 or 2026-06-01T00:00:00."
        ) from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)

    return parsed.astimezone(JST)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot FFT spectra from td-sensor-logger parquet files."
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
        default=Path("plots/fft.png"),
        help="Path to the output PNG file.",
    )
    parser.add_argument(
        "--from",
        dest="from_datetime",
        type=parse_datetime_arg,
        default=None,
        help="Inclusive lower bound in JST. Examples: 2026-06-01, 2026-06-01T00:00:00",
    )
    parser.add_argument(
        "--to",
        dest="to_datetime",
        type=parse_datetime_arg,
        default=None,
        help="Exclusive upper bound in JST. Examples: 2026-06-03, 2026-06-03T00:00:00",
    )
    return parser.parse_args()


def to_epoch_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def load_data(
    data_dir: Path,
    from_datetime: datetime | None = None,
    to_datetime: datetime | None = None,
) -> pl.DataFrame:
    parquet_files = sorted(data_dir.glob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"No parquet files found in {data_dir}")

    lf = pl.scan_parquet(parquet_files)

    if from_datetime is not None:
        lf = lf.filter(pl.col("ts_ms") >= to_epoch_ms(from_datetime))

    if to_datetime is not None:
        lf = lf.filter(pl.col("ts_ms") < to_epoch_ms(to_datetime))

    return (
        lf.with_columns(pl.from_epoch("ts_ms", time_unit="ms").alias("ts"))
        .sort("ts")
        .collect()
    )


def resample_data(df: pl.DataFrame) -> pl.DataFrame:
    return df.group_by_dynamic("ts", every="10m").agg(
        pl.col("temperature_c").mean(),
        pl.col("humidity_pct").mean(),
        pl.col("pressure_hpa").mean(),
    )


def compute_fft_spectrum(values: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]

    if len(values) < 2:
        return np.array([]), np.array([])

    x = np.arange(len(values))
    trend = np.polyval(np.polyfit(x, values, 1), x)
    centered = values - trend
    window = np.hanning(len(centered))
    spectrum = np.fft.rfft(centered * window)
    freqs = np.fft.rfftfreq(len(centered), d=dt)
    amplitude = np.abs(spectrum)

    return freqs[1:], amplitude[1:]


def plot_fft(df_resampled: pl.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    for ax, (column, title, color) in zip(axes, SERIES_SPECS):
        values = df_resampled[column].to_numpy()
        freqs, amplitude = compute_fft_spectrum(values, SAMPLING_INTERVAL_SEC)

        if len(freqs) == 0:
            ax.text(0.5, 0.5, "Not enough data for FFT", ha="center", va="center")
            ax.set_title(title)
            ax.set_ylabel("Amplitude")
            ax.grid(True, alpha=0.3)
            continue

        period_hours = 1 / freqs / 3600
        valid = np.isfinite(period_hours) & (period_hours > 0)

        ax.plot(period_hours[valid], amplitude[valid], color=color, linewidth=1.2)
        ax.set_title(title)
        ax.set_ylabel("Amplitude")
        ax.set_xscale("log")
        ax.axvline(12, color="gray", linestyle="--", linewidth=0.8, alpha=0.7)
        ax.axvline(24, color="gray", linestyle="--", linewidth=0.8, alpha=0.7)

        visible_ticks = TICK_HOURS[
            (TICK_HOURS >= period_hours[valid].min())
            & (TICK_HOURS <= period_hours[valid].max())
        ]
        if len(visible_ticks) > 0:
            ax.xaxis.set_major_locator(
                FixedLocator(visible_ticks)
            )  # ty:ignore[invalid-argument-type]
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Period [hours]")
    fig.suptitle("FFT Spectrum of Temperature, Humidity, and Pressure")
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    df = load_data(args.data_dir, args.from_datetime, args.to_datetime)
    df_resampled = resample_data(df)
    plot_fft(df_resampled, args.output)
    print(f"Saved plot to {args.output}")


if __name__ == "__main__":
    main()
