use anyhow::{Result, bail};
use chrono::Utc;
use polars::prelude::*;
use std::fs::{File, create_dir_all};
use std::path::Path;
use std::process::Command;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::Duration;
use std::time::Instant;

#[derive(Debug, Clone)]
struct Sample {
    ts_ms: i64,
    temperature_c: f64,
    humidity_pct: f64,
    pressure_hpa: f64,
}

fn read_sensor(model_name: &str) -> Result<Sample> {
    // ここを実際のセンサー読み取りに置き換える
    // 例: プログラムの標準出力を読んで parse する

    let output = Command::new("td-usb").args([model_name, "get"]).output()?;
    let out_str = String::from_utf8(output.stdout)?;
    let info = out_str
        .trim()
        .split(",")
        .map(|elem| elem.parse::<f64>())
        .collect::<std::result::Result<Vec<_>, _>>()?;
    let &[temperature_c, humidity_pct, pressure_hpa] = info.as_slice() else {
        bail!("unexpected td-usb output: {:?}", out_str.trim())
    };

    Ok(Sample {
        ts_ms: Utc::now().timestamp_millis(),
        temperature_c,
        humidity_pct,
        pressure_hpa,
    })
}

fn samples_to_df(samples: &[Sample]) -> Result<DataFrame> {
    let ts: Vec<i64> = samples.iter().map(|s| s.ts_ms).collect();
    let temp: Vec<f64> = samples.iter().map(|s| s.temperature_c).collect();
    let hum: Vec<f64> = samples.iter().map(|s| s.humidity_pct).collect();
    let pres: Vec<f64> = samples.iter().map(|s| s.pressure_hpa).collect();

    let df = df![
        "ts_ms" => ts,
        "temperature_c" => temp,
        "humidity_pct" => hum,
        "pressure_hpa" => pres,
    ]?;

    Ok(df)
}

fn flush_to_parquet(samples: &[Sample], out_dir: &str) -> Result<()> {
    if samples.is_empty() {
        return Ok(());
    }

    create_dir_all(out_dir)?;

    let mut df = samples_to_df(samples)?;

    // 必須ではないが、チャンクを整理してから書くと扱いやすい
    df.align_chunks_par();

    let filename = format!(
        "{}/part-{}.parquet",
        out_dir,
        Utc::now().format("%Y%m%d-%H%M%S")
    );

    let file = File::create(&filename)?;

    ParquetWriter::new(file)
        .with_compression(ParquetCompression::Snappy)
        .finish(&mut df)?;

    println!("wrote {} rows to {}", samples.len(), filename);
    Ok(())
}

fn sleep_until_stop(sample_interval: Duration, stop_requested: &AtomicBool) {
    let deadline = Instant::now() + sample_interval;
    let sleep_slice = Duration::from_millis(200);

    while !stop_requested.load(Ordering::Relaxed) {
        let now = Instant::now();
        if now >= deadline {
            break;
        }

        thread::sleep((deadline - now).min(sleep_slice));
    }
}

pub fn run(model_name: &str, sample_interval: Duration, flush_count: usize) -> Result<()> {
    let out_dir = "data";

    if !Path::new(out_dir).exists() {
        create_dir_all(out_dir)?;
    }

    let stop_requested = Arc::new(AtomicBool::new(false));
    {
        let stop_requested = Arc::clone(&stop_requested);
        ctrlc::set_handler(move || {
            stop_requested.store(true, Ordering::Relaxed);
        })?;
    }

    let mut buffer: Vec<Sample> = Vec::new();
    while !stop_requested.load(Ordering::Relaxed) {
        match read_sensor(model_name) {
            Ok(sample) => {
                buffer.push(sample);
            }
            Err(e) => {
                eprintln!("sensor read error: {e:#}");
            }
        }

        if buffer.len() >= flush_count {
            flush_to_parquet(&buffer, out_dir)?;
            buffer.clear();
        }

        sleep_until_stop(sample_interval, &stop_requested);
    }

    flush_to_parquet(&buffer, out_dir)?;
    Ok(())
}
