from __future__ import annotations

import argparse

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
from analyze.forecasting import compare_forecasts


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("forecast", help="短期予測モデルを比較します。")
    add_common_arguments(parser)
    add_time_grid_argument(parser)
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=0.2,
        help="時系列末尾を評価データにする割合",
    )
    parser.add_argument(
        "--valid-ratio",
        type=float,
        default=0.2,
        help="学習期間の末尾を Optuna 検証データにする割合",
    )
    parser.add_argument(
        "--optuna-trials",
        type=int,
        default=25,
        help="各モデルで実行する Optuna trial 数",
    )
    parser.add_argument(
        "--tuning-train-size",
        type=int,
        default=50_000,
        help="各 trial の探索に使う直近の最大学習行数",
    )
    parser.add_argument(
        "--lstm-train-limit",
        type=int,
        default=50_000,
        help="LSTM の学習に使う最大系列数",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> None:
    output_dir = ensure_output_dir(args.output_dir)
    raw_df = load_sensor_data(args.data_dir, DateRange(args.from_datetime, args.to_datetime))
    df = regularize_timeseries(raw_df, args.freq)
    result = compare_forecasts(
        df,
        freq=args.freq,
        test_ratio=args.test_ratio,
        valid_ratio=args.valid_ratio,
        optuna_trials=args.optuna_trials,
        tuning_train_size=args.tuning_train_size,
        lstm_train_limit=args.lstm_train_limit,
    )

    for filename, frame in {
        "forecast_tuning.csv": result.tuning_results,
        "forecast_metrics.csv": result.metrics,
        "forecast_predictions.csv": result.predictions,
    }.items():
        path = output_dir / filename
        save_dataframe(frame, path)
        print_saved(path)

    setup_japanese_matplotlib()
    import matplotlib.pyplot as plt

    pivot = result.metrics.pivot(on="モデル", index="予測対象", values="RMSE")
    target_labels = pivot.get_column("予測対象").to_list()
    model_columns = [column for column in pivot.columns if column != "予測対象"]
    fig, axis = plt.subplots(figsize=(11, 6), constrained_layout=True)
    x = range(len(target_labels))
    width = 0.8 / max(1, len(model_columns))
    for offset, model_name in enumerate(model_columns):
        positions = [value + offset * width for value in x]
        axis.bar(positions, pivot.get_column(model_name).to_list(), width=width, label=model_name)
    axis.set_xticks([value + width * (len(model_columns) - 1) / 2 for value in x], target_labels)
    axis.set_title("短期予測モデル比較(RMSE)")
    axis.set_xlabel("予測対象")
    axis.set_ylabel("RMSE")
    axis.legend(title="モデル")
    axis.grid(True, axis="y", alpha=0.3)
    path = output_dir / "forecast_rmse.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    print_saved(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="短期予測モデルを比較します。")
    add_common_arguments(parser)
    add_time_grid_argument(parser)
    parser.add_argument("--test-ratio", type=float, default=0.2, help="評価データにする割合")
    parser.add_argument("--valid-ratio", type=float, default=0.2, help="Optuna 検証データにする割合")
    parser.add_argument("--optuna-trials", type=int, default=25, help="各モデルの trial 数")
    parser.add_argument("--tuning-train-size", type=int, default=50_000, help="探索用の最大学習行数")
    parser.add_argument("--lstm-train-limit", type=int, default=50_000, help="LSTM の最大学習系列数")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
