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
