# sensor-plotter

`td-sensor-logger` が出力した `data/*.parquet` を読み込み、温度・湿度・気圧の時系列グラフを PNG で生成します。

## Usage

```bash
cd sensor-plotter
uv sync
uv run python main.py
```

出力先を変える場合:

```bash
uv run python main.py --output ../plots/latest.png
```

日時範囲を指定する場合:

```bash
uv run python main.py --from 2026-06-01 --to 2026-06-03
uv run python main.py --to 2026-06-03T09:30:00
```

`--from` は以上、`--to` は未満です。どちらも JST として扱い、`2026-06-01` のような日付だけの指定もできます。

FFT プロットも同じ引数で実行できます。

```bash
uv run python fft_.py --from 2026-06-01 --to 2026-06-03
uv run python fft_.py --output ../plots/fft-latest.png
```
