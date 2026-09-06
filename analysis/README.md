# センサーデータ分析

`td-sensor-logger` が `data/*.parquet` に保存した気温、相対湿度、気圧を分析します。

## セットアップ

```bash
cd analysis
uv sync
```

Python は `.python-version` と `pyproject.toml` に合わせて 3.14 を使います。

## 基本統計

平均、中央値、最大、最小、標準偏差、日ごと・週ごと・月ごとの集計、欠損値、IQR による異常値を出力します。

```bash
uv run analyze-stats --data-dir ../data
```

主な出力:

- `outputs/basic_statistics.csv`
- `outputs/daily_summary.csv`
- `outputs/weekly_summary.csv`
- `outputs/monthly_summary.csv`
- `outputs/quality_report.csv`
- `outputs/sensor_timeseries.png`

## 相関分析

気温と湿度、気圧と気温、気圧低下後の湿度変化、10 分・30 分・1 時間ラグの相関を出力します。
取得時刻のずれを避けるため、既定では 1 分グリッドに平均リサンプルして補間します。

```bash
uv run analyze-correlations --data-dir ../data
uv run analyze-correlations --data-dir ../data --freq 5m
```

主な出力:

- `outputs/simultaneous_correlations.csv`
- `outputs/lag_correlations.csv`
- `outputs/pressure_drop_humidity_effect.csv`
- `outputs/correlation_scatter.png`
- `outputs/lag_correlations_top.png`

## 派生指標

気温と相対湿度から、露点温度、絶対湿度、不快指数を算出します。

```bash
uv run analyze-derived --data-dir ../data
```

主な出力:

- `outputs/derived_metrics.csv`
- `outputs/derived_metrics.png`

## 短期予測

過去値、ラグ特徴量、露点温度、絶対湿度、不快指数を使い、次の対象を予測してモデルを比較します。

- 10 分後の気温
- 1 時間後の湿度
- 3 時間後の気圧

```bash
uv run analyze-forecast --data-dir ../data
```

Optuna の trial 数や探索に使う学習行数を変える場合:

```bash
uv run analyze-forecast --data-dir ../data --optuna-trials 50 --tuning-train-size 80000 --lstm-train-limit 80000
```

比較対象:

- Ridge 回帰
- Random Forest
- 勾配ブースティング
- LightGBM
- LSTM

主な出力:

- `outputs/forecast_tuning.csv`
- `outputs/forecast_metrics.csv`
- `outputs/forecast_predictions.csv`
- `outputs/forecast_rmse.png`

## 範囲指定

各コマンドで `--from` と `--to` を指定できます。どちらも JST として扱います。

```bash
uv run analyze-stats --data-dir ../data --from 2026-06-01 --to 2026-06-03
```

## 文字化け対策

PNG を出力するコマンドでは `matplotlib_fontja` を読み込み、日本語ラベルの文字化けを避けています。
