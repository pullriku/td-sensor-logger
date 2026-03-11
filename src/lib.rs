use anyhow::{Context, Result, bail};
use chrono::{Local, Utc};
use polars::prelude::*;
use signal_hook::consts::signal::{SIGINT, SIGTERM, SIGUSR1};
use signal_hook::flag;
use std::fs::{File, create_dir_all};
use std::path::Path;
use std::process::Command;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{Receiver, SyncSender, sync_channel};
use std::thread;
use std::time::{Duration, Instant};

const WRITER_QUEUE_CAPACITY: usize = 8;
const WAIT_SLICE: Duration = Duration::from_millis(50);

#[derive(Debug, Clone, PartialEq)]
struct Sample {
    ts_ms: i64,
    temperature_c: f64,
    humidity_pct: f64,
    pressure_hpa: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum LoopEvent {
    SampleDue,
    FlushRequested,
    StopRequested,
}

fn read_sensor(model_name: &str) -> Result<Sample> {
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
    df.align_chunks_par();

    let filename = format!(
        "{}/{}.parquet",
        out_dir,
        Local::now().format("%Y%m%d-%H%M%S-%:z")
    );

    let file = File::create(&filename)?;

    ParquetWriter::new(file)
        .with_compression(ParquetCompression::Snappy)
        .finish(&mut df)?;

    println!("wrote {} rows to {}", samples.len(), filename);
    Ok(())
}

fn wait_for_event(
    next_sample_at: Instant,
    stop_requested: &AtomicBool,
    flush_requested: &AtomicBool,
) -> LoopEvent {
    loop {
        if stop_requested.load(Ordering::Relaxed) {
            return LoopEvent::StopRequested;
        }

        if flush_requested.swap(false, Ordering::Relaxed) {
            return LoopEvent::FlushRequested;
        }

        let now = Instant::now();
        if now >= next_sample_at {
            return LoopEvent::SampleDue;
        }

        thread::sleep((next_sample_at - now).min(WAIT_SLICE));
    }
}

fn enqueue_buffer(sender: &SyncSender<Vec<Sample>>, buffer: &mut Vec<Sample>) -> Result<()> {
    if buffer.is_empty() {
        return Ok(());
    }

    let batch = std::mem::take(buffer);
    sender
        .send(batch)
        .context("writer thread stopped before flush queue was drained")
}

fn writer_loop<F>(receiver: Receiver<Vec<Sample>>, mut flush_fn: F) -> Result<()>
where
    F: FnMut(&[Sample]) -> Result<()>,
{
    while let Ok(samples) = receiver.recv() {
        if samples.is_empty() {
            continue;
        }

        flush_fn(&samples)?;
    }

    Ok(())
}

fn spawn_writer(
    out_dir: String,
    receiver: Receiver<Vec<Sample>>,
) -> thread::JoinHandle<Result<()>> {
    thread::spawn(move || writer_loop(receiver, |samples| flush_to_parquet(samples, &out_dir)))
}

pub fn run(model_name: &str, sample_interval: Duration, flush_count: usize) -> Result<()> {
    let out_dir = "data";

    if !Path::new(out_dir).exists() {
        create_dir_all(out_dir)?;
    }

    let stop_requested = Arc::new(AtomicBool::new(false));
    let flush_requested = Arc::new(AtomicBool::new(false));
    flag::register(SIGINT, Arc::clone(&stop_requested))?;
    flag::register(SIGTERM, Arc::clone(&stop_requested))?;
    flag::register(SIGUSR1, Arc::clone(&flush_requested))?;

    let (sender, receiver) = sync_channel::<Vec<Sample>>(WRITER_QUEUE_CAPACITY);
    let writer_handle = spawn_writer(out_dir.to_string(), receiver);

    let run_result = (|| -> Result<()> {
        let mut buffer = Vec::new();
        let mut next_sample_at = Instant::now();

        loop {
            match wait_for_event(next_sample_at, &stop_requested, &flush_requested) {
                LoopEvent::SampleDue => {
                    match read_sensor(model_name) {
                        Ok(sample) => {
                            buffer.push(sample);
                            if buffer.len() >= flush_count {
                                enqueue_buffer(&sender, &mut buffer)?;
                            }
                        }
                        Err(e) => {
                            eprintln!("sensor read error: {e:#}");
                        }
                    }

                    let scheduled_next = next_sample_at + sample_interval;
                    next_sample_at = scheduled_next.max(Instant::now());
                }
                LoopEvent::FlushRequested => {
                    enqueue_buffer(&sender, &mut buffer)?;
                    println!("flush requested via SIGUSR1");
                }
                LoopEvent::StopRequested => {
                    enqueue_buffer(&sender, &mut buffer)?;
                    break;
                }
            }
        }

        Ok(())
    })();

    drop(sender);

    let writer_result = writer_handle
        .join()
        .map_err(|_| anyhow::anyhow!("writer thread panicked"))?;

    run_result.and(writer_result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    fn sample(ts_ms: i64) -> Sample {
        Sample {
            ts_ms,
            temperature_c: 20.0,
            humidity_pct: 50.0,
            pressure_hpa: 1013.0,
        }
    }

    #[test]
    fn wait_for_event_returns_flush_immediately() {
        let stop_requested = AtomicBool::new(false);
        let flush_requested = AtomicBool::new(true);
        let started_at = Instant::now();

        let event = wait_for_event(
            started_at + Duration::from_millis(200),
            &stop_requested,
            &flush_requested,
        );

        assert_eq!(event, LoopEvent::FlushRequested);
        assert!(started_at.elapsed() < Duration::from_millis(50));
    }

    #[test]
    fn wait_for_event_prefers_stop() {
        let stop_requested = AtomicBool::new(true);
        let flush_requested = AtomicBool::new(true);

        let event = wait_for_event(
            Instant::now() + Duration::from_secs(1),
            &stop_requested,
            &flush_requested,
        );

        assert_eq!(event, LoopEvent::StopRequested);
    }

    #[test]
    fn enqueue_buffer_moves_samples_and_clears_buffer() {
        let (sender, receiver) = sync_channel(1);
        let mut buffer = vec![sample(1), sample(2)];

        enqueue_buffer(&sender, &mut buffer).unwrap();

        assert!(buffer.is_empty());
        assert_eq!(receiver.recv().unwrap(), vec![sample(1), sample(2)]);
    }

    #[test]
    fn enqueue_buffer_skips_empty_batches() {
        let (sender, receiver) = sync_channel(1);
        let mut buffer = Vec::new();

        enqueue_buffer(&sender, &mut buffer).unwrap();

        assert!(receiver.try_recv().is_err());
    }

    #[test]
    fn writer_loop_skips_empty_batches_and_preserves_order() {
        let (sender, receiver) = sync_channel(4);
        let written = Mutex::new(Vec::<Vec<Sample>>::new());

        sender.send(vec![sample(1)]).unwrap();
        sender.send(Vec::new()).unwrap();
        sender.send(vec![sample(2), sample(3)]).unwrap();
        drop(sender);

        writer_loop(receiver, |samples| {
            written.lock().unwrap().push(samples.to_vec());
            Ok(())
        })
        .unwrap();

        assert_eq!(
            written.into_inner().unwrap(),
            vec![vec![sample(1)], vec![sample(2), sample(3)]]
        );
    }
}
