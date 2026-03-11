# td-sensor-logger

東京デバイセズの USB 温度・湿度・気圧センサ [`TDSN7200`](https://tokyodevices.com/items/327?srsltid=AfmBOoqqai4qP3UvxIijZmnyYZUMB6M9nDpf91o0zKIFW3eNnbLab3Gm) を、[`td-usb`](https://github.com/tokyodevices/td-usb) 経由で定期取得し、`Parquet` で保存するロガーです。

保存先は `data/`、可視化用に `sensor-plotter/` も同梱しています。

## できること

- 一定間隔でセンサー値を取得
- メモリ上でバッファしてまとめて `Parquet` に書き出し
- `SIGUSR1` で手動フラッシュ
- `SIGINT` / `SIGTERM` で停止時フラッシュ

## 前提

- Rust ツールチェイン
- `td-usb` コマンドが使えること
- 対象センサーが `td-usb <model> get` で読めること

デフォルトのモデル名は `tdsn7200` です。

`td-usb` 自体は東京デバイセズ提供の USB デバイス用 CLI です。Linux では公式 README にある通り、ビルド時に `libusb-dev` が必要です。

## ビルド

```bash
cargo build --release
```

実行ファイルは `target/release/td-sensor-logger` に生成されます。

## 使い方

### 直接実行

```bash
cargo run --release -- tdsn7200 --interval 60 --flush-count 10000
```

引数:

- `model_name`: センサーモデル名。省略時は `tdsn7200`
- `--interval`: 取得間隔（秒）。省略時は `60`
- `--flush-count`: 何件たまったら書き出すか。省略時は `10000`

内部的には `td-usb tdsn7200 get` を一定間隔で呼び出し、`温度(℃),湿度(%),気圧(hPa)` の順で返る値を保存します。

### 付属スクリプト

バックグラウンド起動:

```bash
./start.sh
```

テスト用の短い間隔で起動:

```bash
./start_test.sh
```

停止:

```bash
./stop.sh
```

手動フラッシュ:

```bash
./flush.sh
```

`start.sh` / `start_test.sh` は `logger.pid` と `logger.log` を作成します。

## 出力

ログは `data/*.parquet` に保存されます。ファイル名はローカル時刻ベースです。

カラム:

- `ts_ms`
- `temperature_c`
- `humidity_pct`
- `pressure_hpa`

## 運用メモ

- 読み取りエラーは標準エラー出力に出しつつ継続します
- `flush-count` に達しなくても、停止時と `SIGUSR1` 受信時にバッファを書き出します
- 書き出しは Snappy 圧縮の Parquet です

## 可視化

`sensor-plotter/` で `data/*.parquet` を PNG にできます。

```bash
cd sensor-plotter
uv sync
uv run python main.py
```

## just

`just` が入っていれば次も使えます。

```bash
just start
just flush
just stop
just plot
```
