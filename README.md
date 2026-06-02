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

### systemd user service

ログインしていなくても自動起動したい場合は、`systemd --user` サービスとして動かせます。
この方法なら、ロガー本体は通常ユーザー権限で動き、`SIGUSR1` による手動フラッシュも維持できます。

1. まず release build します。

```bash
cargo build --release
```

2. 設定ファイルを作ります。

```bash
cp systemd/user/td-sensor-logger.env.example systemd/user/td-sensor-logger.env
```

必要なら `MODEL_NAME` / `INTERVAL` / `FLUSH_COUNT` を編集してください。

3. user service を登録して起動します。

```bash
mkdir -p ~/.config/systemd/user
ln -sf "$PWD/systemd/user/td-sensor-logger.service" ~/.config/systemd/user/td-sensor-logger.service
systemctl --user daemon-reload
systemctl --user enable --now td-sensor-logger.service
```

状態確認:

```bash
systemctl --user status td-sensor-logger.service
journalctl --user -u td-sensor-logger.service -f
```

手動フラッシュ:

```bash
systemctl --user reload td-sensor-logger.service
```

停止:

```bash
systemctl --user stop td-sensor-logger.service
```

付属スクリプトでも同じ操作ができます。

起動:

```bash
./start.sh
```

停止:

```bash
./stop.sh
```

手動フラッシュ:

```bash
./flush.sh
```

起動時に自動起動させるには、管理者権限で linger を有効にしてください。

```bash
sudo loginctl enable-linger "$USER"
```

これで OS 起動時に `td-sensor-logger.service` が立ち上がります。
リポジトリを別の場所へ移した場合は、[`systemd/user/td-sensor-logger.service`](/home/tatsumi/projects/td-sensor-logger/systemd/user/td-sensor-logger.service) の `WorkingDirectory` と `ExecStart` を合わせて更新してください。

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

範囲指定する場合:

```bash
uv run python main.py --from 2026-06-01 --to 2026-06-03
uv run python main.py --from 2026-06-01T12:00:00
```

`--from` は以上、`--to` は未満です。どちらも JST として解釈され、日付だけを指定した場合は `00:00:00` 扱いになります。

FFT プロットも同様に範囲指定できます。

## just

`just` が入っていれば次も使えます。

```bash
just start
just flush
just stop
just status
just logs
just plot
just plot-from 2026-06-01
just plot-to 2026-06-03T09:30:00
just plot-range 2026-06-01 2026-06-03
```
