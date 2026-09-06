from __future__ import annotations

import argparse

import polars as pl

from analyze.common import (
    DateRange,
    add_common_arguments,
    add_time_grid_argument,
    ensure_output_dir,
    load_sensor_data,
    print_saved,
    regularize_timeseries,
    save_dataframe,
    setup_japanese_matplotlib,
)
from analyze.correlation import (
    lag_correlations,
    pressure_drop_humidity_effect,
    simultaneous_correlations,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("correlations", help="同時刻相関とラグ相関を出力します。")
    add_common_arguments(parser)
    add_time_grid_argument(parser)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> None:
    output_dir = ensure_output_dir(args.output_dir)
    raw_df = load_sensor_data(args.data_dir, DateRange(args.from_datetime, args.to_datetime))
    df = regularize_timeseries(raw_df, args.freq)

    corr = simultaneous_correlations(df)
    lag = lag_correlations(df, args.freq)
    pressure_effect = pressure_drop_humidity_effect(df, args.freq)
    pressure_effect_corr = pressure_effect.select(
        pl.corr("気圧変化_hpa", "湿度変化_pct").alias("相関係数")
    )

    for filename, frame in {
        "simultaneous_correlations.csv": corr,
        "lag_correlations.csv": lag,
        "pressure_drop_humidity_effect.csv": pressure_effect,
        "pressure_drop_humidity_correlation.csv": pressure_effect_corr,
    }.items():
        path = output_dir / filename
        save_dataframe(frame, path)
        print_saved(path)

    setup_japanese_matplotlib()
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    axes[0].scatter(
        df.get_column("temperature_c").to_list(),
        df.get_column("humidity_pct").to_list(),
        s=12,
        alpha=0.45,
        color="#0369a1",
    )
    axes[0].set_title("気温と湿度")
    axes[0].set_xlabel("気温(℃)")
    axes[0].set_ylabel("湿度(%)")
    axes[0].grid(True, alpha=0.3)

    axes[1].scatter(
        df.get_column("pressure_hpa").to_list(),
        df.get_column("temperature_c").to_list(),
        s=12,
        alpha=0.45,
        color="#b45309",
    )
    axes[1].set_title("気圧と気温")
    axes[1].set_xlabel("気圧(hPa)")
    axes[1].set_ylabel("気温(℃)")
    axes[1].grid(True, alpha=0.3)
    path = output_dir / "correlation_scatter.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    print_saved(path)

    top_lag = (
        lag.with_columns(pl.col("相関係数").abs().alias("abs_corr"))
        .sort("abs_corr", descending=True)
        .head(20)
    )
    labels = [
        f"{row['過去の項目']}→{row['現在の項目']}({row['遅れ']})"
        for row in top_lag.iter_rows(named=True)
    ]
    fig, axis = plt.subplots(figsize=(12, 7), constrained_layout=True)
    axis.barh(labels, top_lag.get_column("相関係数").to_list(), color="#0f766e")
    axis.invert_yaxis()
    axis.set_xlabel("相関係数")
    axis.set_title("ラグ相関の上位")
    axis.grid(True, axis="x", alpha=0.3)
    path = output_dir / "lag_correlations_top.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    print_saved(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="同時刻相関とラグ相関を出力します。")
    add_common_arguments(parser)
    add_time_grid_argument(parser)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
