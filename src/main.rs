use std::time::Duration;

use anyhow::{Result, ensure};
use clap::Parser;
use td_sensor_logger::run;

#[derive(clap::Parser)]
struct Cli {
    #[arg(default_value = "tdsn7200")]
    model_name: String,

    #[arg(long, default_value_t = 60)]
    interval: u64,

    #[arg(long, default_value_t = 10000)]
    flush_count: usize,
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    ensure!(cli.flush_count > 0, "--flush-count must be greater than 0");

    run(
        &cli.model_name,
        Duration::from_secs(cli.interval),
        cli.flush_count,
    )?;

    Ok(())
}
