from __future__ import annotations

import polars as pl

from .common import SENSOR_COLUMNS


def basic_statistics(df: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for label, expr_name in [
        ("平均", "mean"),
        ("中央値", "median"),
        ("最大", "max"),
        ("最小", "min"),
        ("標準偏差", "std"),
    ]:
        row = {"統計量": label}
        for column in SENSOR_COLUMNS:
            row[column] = df.select(getattr(pl.col(column), expr_name)()).item()
        rows.append(row)
    return pl.DataFrame(rows)


def aggregate_by_period(df: pl.DataFrame, period: str) -> pl.DataFrame:
    expressions = []
    for column in SENSOR_COLUMNS:
        expressions.extend(
            [
                pl.col(column).mean().alias(f"{column}_平均"),
                pl.col(column).median().alias(f"{column}_中央値"),
                pl.col(column).max().alias(f"{column}_最大"),
                pl.col(column).min().alias(f"{column}_最小"),
                pl.col(column).std().alias(f"{column}_標準偏差"),
            ]
        )
    return (
        df.sort("timestamp")
        .group_by_dynamic("timestamp", every=period)
        .agg(expressions)
        .sort("timestamp")
    )


def quality_report(df: pl.DataFrame) -> pl.DataFrame:
    rows = []
    row_count = df.height
    for column in SENSOR_COLUMNS:
        q1 = df.select(pl.col(column).quantile(0.25)).item()
        q3 = df.select(pl.col(column).quantile(0.75)).item()
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        missing_count = df.select(pl.col(column).is_null().sum()).item()
        outlier_count = df.filter((pl.col(column) < lower) | (pl.col(column) > upper)).height
        rows.append(
            {
                "項目": column,
                "欠損数": int(missing_count),
                "欠損率": float(missing_count / row_count) if row_count else 0.0,
                "異常値数(IQR)": int(outlier_count),
                "異常値下限(IQR)": float(lower),
                "異常値上限(IQR)": float(upper),
            }
        )
    return pl.DataFrame(rows)
