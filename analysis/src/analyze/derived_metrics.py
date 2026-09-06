from __future__ import annotations

import polars as pl


def add_derived_metrics(df: pl.DataFrame) -> pl.DataFrame:
    temp_c = pl.col("temperature_c").cast(pl.Float64)
    rh_pct = pl.col("humidity_pct").cast(pl.Float64).clip(0.0, 100.0)
    gamma = (rh_pct / 100.0).log() + (17.625 * temp_c) / (243.04 + temp_c)
    saturation_vapor_pressure_hpa = 6.112 * ((17.67 * temp_c) / (temp_c + 243.5)).exp()
    vapor_pressure_hpa = (rh_pct / 100.0) * saturation_vapor_pressure_hpa

    return df.with_columns(
        [
            ((243.04 * gamma) / (17.625 - gamma)).alias("dew_point_c"),
            (216.7 * vapor_pressure_hpa / (temp_c + 273.15)).alias(
                "absolute_humidity_g_m3"
            ),
            (0.81 * temp_c + 0.01 * rh_pct * (0.99 * temp_c - 14.3) + 46.3).alias(
                "discomfort_index"
            ),
        ]
    )
