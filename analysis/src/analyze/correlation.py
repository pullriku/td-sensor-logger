from __future__ import annotations

import polars as pl

from .common import SENSOR_COLUMNS, periods_for_duration


DEFAULT_LAGS = {
    "10m": "10m",
    "30m": "30m",
    "1h": "1h",
}


def _corr_value(df: pl.DataFrame, left: str, right: str) -> float | None:
    return df.select(pl.corr(left, right)).item()


def simultaneous_correlations(df: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for left in SENSOR_COLUMNS:
        row = {"項目": left}
        for right in SENSOR_COLUMNS:
            row[right] = _corr_value(df, left, right)
        rows.append(row)
    return pl.DataFrame(rows)


def lag_correlations(
    df: pl.DataFrame,
    freq: str,
    target_columns: list[str] | None = None,
    lags: dict[str, str] | None = None,
) -> pl.DataFrame:
    if target_columns is None:
        target_columns = SENSOR_COLUMNS
    if lags is None:
        lags = DEFAULT_LAGS

    rows = []
    for lag_label, lag_value in lags.items():
        periods = periods_for_duration(lag_value, freq)
        shifted = df.with_columns(
            [pl.col(column).shift(periods).alias(f"{column}_lag") for column in SENSOR_COLUMNS]
        )
        for source in SENSOR_COLUMNS:
            source_column = f"{source}_lag"
            for target in target_columns:
                valid = shifted.select([source_column, target]).drop_nulls()
                rows.append(
                    {
                        "遅れ": lag_label,
                        "過去の項目": source,
                        "現在の項目": target,
                        "相関係数": _corr_value(valid, source_column, target)
                        if valid.height >= 2
                        else None,
                        "件数": valid.height,
                    }
                )
    return pl.DataFrame(rows)


def pressure_drop_humidity_effect(
    df: pl.DataFrame,
    freq: str,
    pressure_window: str = "30m",
    humidity_window: str = "1h",
) -> pl.DataFrame:
    pressure_periods = periods_for_duration(pressure_window, freq)
    humidity_periods = periods_for_duration(humidity_window, freq)
    return (
        df.with_columns(
            [
                (pl.col("pressure_hpa") - pl.col("pressure_hpa").shift(pressure_periods)).alias(
                    "気圧変化_hpa"
                ),
                (pl.col("humidity_pct").shift(-humidity_periods) - pl.col("humidity_pct")).alias(
                    "湿度変化_pct"
                ),
            ]
        )
        .select(["timestamp", "気圧変化_hpa", "湿度変化_pct"])
        .drop_nulls()
    )
