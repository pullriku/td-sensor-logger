import polars as pl
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter

# Parquet 読み込み
df = pl.read_parquet("../data/*.parquet")

# ts_ms → datetime に変換してソート
df = (
    df
    .with_columns(pl.from_epoch("ts_ms", time_unit="ms").alias("ts"))
    .sort("ts")
)

# --- リサンプル（10分間隔に統一） ---
df_resampled = (
    df
    .group_by_dynamic("ts", every="10m")
    .agg(
        pl.col("temperature_c").mean(),
        pl.col("humidity_pct").mean(),
        pl.col("pressure_hpa").mean(),
    )
)

sampling_interval_sec = 10 * 60


def compute_fft_spectrum(values: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]

    if len(values) < 2:
        return np.array([]), np.array([])

    # 平均値を引いて直流成分を落とし、変動だけを見やすくする
    # centered = values - np.mean(values)
    x = np.arange(len(values))
    trend = np.polyval(np.polyfit(x, values, 1), x)
    centered = values - trend
    # spectrum = np.fft.rfft(centered)
    window = np.hanning(len(centered))
    spectrum = np.fft.rfft(centered * window)
    freqs = np.fft.rfftfreq(len(centered), d=dt)
    amplitude = np.abs(spectrum)

    return freqs[1:], amplitude[1:]


series_specs = [
    ("temperature_c", "Temperature", "tab:red"),
    ("humidity_pct", "Humidity", "tab:blue"),
    ("pressure_hpa", "Pressure", "tab:green"),
]

tick_hours = np.array([0.5, 1, 2, 3, 6, 12, 24, 48, 72, 168], dtype=float)

fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

for ax, (column, title, color) in zip(axes, series_specs):
    values = df_resampled[column].to_numpy()
    freqs, amplitude = compute_fft_spectrum(values, sampling_interval_sec)

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
    visible_ticks = tick_hours[(tick_hours >= period_hours[valid].min()) & (tick_hours <= period_hours[valid].max())]
    if len(visible_ticks) > 0:
        ax.xaxis.set_major_locator(FixedLocator(visible_ticks))  # ty:ignore[invalid-argument-type]
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
    ax.grid(True, alpha=0.3)

axes[-1].set_xlabel("Period [hours]")
fig.suptitle("FFT Spectrum of Temperature, Humidity, and Pressure")
fig.tight_layout()
plt.savefig("plots/fft.png")
