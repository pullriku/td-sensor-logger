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
from analyze.derived_metrics import add_derived_metrics


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("derived", help="露点温度、絶対湿度、不快指数を算出します。")
    add_common_arguments(parser)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> None:
    output_dir = ensure_output_dir(args.output_dir)
    df = load_sensor_data(args.data_dir, DateRange(args.from_datetime, args.to_datetime))
    derived = add_derived_metrics(df)

    path = output_dir / "derived_metrics.csv"
    save_dataframe(
        derived.select(
            [
                "timestamp",
                "temperature_c",
                "humidity_pct",
                "pressure_hpa",
                "dew_point_c",
                "absolute_humidity_g_m3",
                "discomfort_index",
            ]
        ),
        path,
    )
    print_saved(path)

    setup_japanese_matplotlib()
    import matplotlib.pyplot as plt

    timestamps = derived.get_column("timestamp").to_list()
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True, constrained_layout=True)
    axes[0].plot(
        timestamps,
        derived.get_column("temperature_c").to_list(),
        label="気温",
        color="#b45309",
    )
    axes[0].plot(
        timestamps,
        derived.get_column("dew_point_c").to_list(),
        label="露点温度",
        color="#0f766e",
    )
    axes[0].set_ylabel("温度(℃)")
    axes[0].legend()

    axes[1].plot(
        timestamps,
        derived.get_column("humidity_pct").to_list(),
        label="相対湿度",
        color="#0369a1",
    )
    axes[1].set_ylabel("相対湿度(%)")
    axes[1].legend()

    axes[2].plot(
        timestamps,
        derived.get_column("absolute_humidity_g_m3").to_list(),
        label="絶対湿度",
        color="#7c3aed",
    )
    axes[2].plot(
        timestamps,
        derived.get_column("discomfort_index").to_list(),
        label="不快指数",
        color="#be123c",
    )
    axes[2].set_ylabel("派生指標")
    axes[2].set_xlabel("時刻")
    axes[2].legend()

    for axis in axes:
        axis.grid(True, alpha=0.3)
    fig.suptitle("露点温度・絶対湿度・不快指数")
    path = output_dir / "derived_metrics.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    print_saved(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="露点温度、絶対湿度、不快指数を算出します。")
    add_common_arguments(parser)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
