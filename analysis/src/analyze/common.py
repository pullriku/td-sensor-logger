from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl


JST = ZoneInfo("Asia/Tokyo")
JST_NAME = "Asia/Tokyo"
SENSOR_COLUMNS = ["temperature_c", "humidity_pct", "pressure_hpa"]
METRIC_LABELS = {
    "temperature_c": "気温(℃)",
    "humidity_pct": "相対湿度(%)",
    "pressure_hpa": "気圧(hPa)",
    "dew_point_c": "露点温度(℃)",
    "absolute_humidity_g_m3": "絶対湿度(g/m3)",
    "discomfort_index": "不快指数",
}


@dataclass(frozen=True)
class DateRange:
    from_datetime: datetime | None = None
    to_datetime: datetime | None = None


def parse_datetime_arg(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "日時は 2026-06-01 または 2026-06-01T00:00:00 の形式で指定してください。"
        ) from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)

    return parsed.astimezone(JST)


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("../data"),
        help="td-sensor-logger が書き出した parquet ファイルのディレクトリ",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="CSV や PNG の出力先ディレクトリ",
    )
    parser.add_argument(
        "--from",
        dest="from_datetime",
        type=parse_datetime_arg,
        default=None,
        help="JST の開始日時(以上)。例: 2026-06-01, 2026-06-01T00:00:00",
    )
    parser.add_argument(
        "--to",
        dest="to_datetime",
        type=parse_datetime_arg,
        default=None,
        help="JST の終了日時(未満)。例: 2026-06-03, 2026-06-03T00:00:00",
    )


def add_time_grid_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--freq",
        default="1m",
        help="ラグ相関や予測で使う時間グリッド。例: 1m, 5m, 10m",
    )


def load_sensor_data(
    data_dir: Path,
    date_range: DateRange | None = None,
) -> pl.DataFrame:
    parquet_files = sorted(data_dir.glob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"{data_dir} に parquet ファイルがありません。")

    df = (
        pl.scan_parquet(parquet_files)
        .unique(subset=["ts_ms"])
        .sort("ts_ms")
        .with_columns(
            pl.from_epoch("ts_ms", time_unit="ms")
            .dt.replace_time_zone("UTC")
            .dt.convert_time_zone(JST_NAME)
            .alias("timestamp")
        )
        .collect()
    )
    required = {"ts_ms", *SENSOR_COLUMNS}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"必要なカラムがありません: {', '.join(sorted(missing))}")

    if date_range is not None:
        if date_range.from_datetime is not None:
            df = df.filter(pl.col("timestamp") >= date_range.from_datetime)
        if date_range.to_datetime is not None:
            df = df.filter(pl.col("timestamp") < date_range.to_datetime)

    if df.is_empty():
        raise ValueError("指定範囲にデータがありません。")

    return df


def ensure_output_dir(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def regularize_timeseries(df: pl.DataFrame, freq: str) -> pl.DataFrame:
    regularized = (
        df.sort("timestamp")
        .group_by_dynamic("timestamp", every=freq)
        .agg([pl.col(column).mean() for column in SENSOR_COLUMNS])
        .sort("timestamp")
        .upsample(time_column="timestamp", every=freq)
        .with_columns([pl.col(column).interpolate() for column in SENSOR_COLUMNS])
        .drop_nulls(SENSOR_COLUMNS)
    )
    if regularized.is_empty():
        raise ValueError("時間グリッド化後に有効データがありません。--freq を確認してください。")
    return regularized


def save_dataframe(df: pl.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(output_path)


def setup_japanese_matplotlib() -> None:
    import matplotlib_fontja  # noqa: F401


def print_saved(path: Path) -> None:
    print(f"保存しました: {path}")


def metric_label(metric: str) -> str:
    return METRIC_LABELS.get(metric, metric)


def column_values(df: pl.DataFrame, column: str) -> list[object]:
    return df.get_column(column).to_list()


def duration_to_minutes(value: str) -> int:
    normalized = value.strip().lower()
    if normalized.endswith("min"):
        return int(normalized[:-3])
    if normalized.endswith("m"):
        return int(normalized[:-1])
    if normalized.endswith("hour"):
        return int(normalized[:-4]) * 60
    if normalized.endswith("h"):
        return int(normalized[:-1]) * 60
    raise ValueError(f"未対応の時間指定です: {value}")


def periods_for_duration(duration: str, freq: str) -> int:
    duration_minutes = duration_to_minutes(duration)
    freq_minutes = duration_to_minutes(freq)
    if freq_minutes <= 0:
        raise ValueError("--freq は 0 より大きい時間にしてください。")
    periods = duration_minutes / freq_minutes
    if not periods.is_integer():
        raise ValueError(f"{duration} は --freq {freq} の整数倍ではありません。")
    return int(periods)
