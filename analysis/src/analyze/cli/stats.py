from __future__ import annotations

import argparse

from analyze.common import (
    DateRange,
    add_common_arguments,
    ensure_output_dir,
    load_sensor_data,
    print_saved,
    save_dataframe,
    setup_japanese_matplotlib,
)
from analyze.stats import aggregate_by_period, basic_statistics, quality_report


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("stats", help="基本統計、期間集計、欠損値、異常値を出力します。")
    add_common_arguments(parser)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> None:
    output_dir = ensure_output_dir(args.output_dir)
    df = load_sensor_data(args.data_dir, DateRange(args.from_datetime, args.to_datetime))

    basic = basic_statistics(df)
    quality = quality_report(df)
    daily = aggregate_by_period(df, "1d")
    weekly = aggregate_by_period(df, "1w")
    monthly = aggregate_by_period(df, "1mo")

    outputs = {
        "basic_statistics.csv": basic,
        "quality_report.csv": quality,
        "daily_summary.csv": daily,
        "weekly_summary.csv": weekly,
        "monthly_summary.csv": monthly,
    }
    for filename, frame in outputs.items():
        path = output_dir / filename
        save_dataframe(frame, path)
        print_saved(path)

    setup_japanese_matplotlib()
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True, constrained_layout=True)
    timestamps = df.get_column("timestamp").to_list()
    axes[0].plot(
        timestamps,
        df.get_column("temperature_c").to_list(),
        color="#b45309",
        linewidth=1.4,
    )
    axes[0].set_ylabel("気温(℃)")
    axes[1].plot(
        timestamps,
        df.get_column("humidity_pct").to_list(),
        color="#0369a1",
        linewidth=1.4,
    )
    axes[1].set_ylabel("湿度(%)")
    axes[2].plot(
        timestamps,
        df.get_column("pressure_hpa").to_list(),
        color="#4d7c0f",
        linewidth=1.4,
    )
    axes[2].set_ylabel("気圧(hPa)")
    axes[2].set_xlabel("時刻")
    for axis in axes:
        axis.grid(True, alpha=0.3)
    fig.suptitle("センサー値の時系列")
    path = output_dir / "sensor_timeseries.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    print_saved(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="基本統計、期間集計、欠損値、異常値を出力します。")
    add_common_arguments(parser)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
