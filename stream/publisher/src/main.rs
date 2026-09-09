//! Streams a continuously running Tennessee Eastman plant as OPC UA
//! `DataValue` records in a Sparkplug-shaped envelope, one JSON object per
//! line on stdout, for a broker to publish.
//!
//! Two clocks matter and the whole assignment turns on telling them apart.
//! `sourceTimestamp` is when the instrument read the value, which is plant
//! time; the message-level `timestamp` is when this publisher forwarded it,
//! and is the OPC UA `ServerTimestamp` for every `DataValue` in the batch.
//! They differ whenever a batch is held and forwarded late, which is what a
//! store-and-forward historian does after a link comes back. The server
//! timestamp is carried once per message rather than once per metric because
//! a batch is forwarded as a unit, so 53 copies of it would be 53 copies of
//! the same instant.

mod rng;
mod tags;
mod time;

use std::io::{BufWriter, Write};
use tepsim::{Scenario, Simulation};

/// Plant hours between fault episodes. Exactly one onset per block, so any
/// window this long contains at least one, whenever a student happens to run.
const BLOCK_HOURS: f64 = 12.0;

/// The disturbances the schedule draws from. IDV(6), a total loss of A feed,
/// is left out because it walks the plant into a shutdown rather than
/// perturbing it. IDV(17), (18) and (20) are in on purpose: they are the
/// random-walk and spike-train channels, and the hardest of the twenty to see.
/// IDV(7) is left out for a subtler reason than IDV(6): the plant rides it
/// out fine and then trips on reactor pressure about half an hour *after* it
/// clears, because restoring the C header pressure in one step over-pressures
/// a reactor whose controllers have wound up against the loss. No published
/// TEP dataset shows this, because they all start a fault and run to the end
/// of the file without ever switching one off.
const FAULTS: [usize; 13] = [1, 2, 4, 5, 8, 10, 11, 12, 13, 14, 17, 18, 20];

struct Args {
    speed: f64,
    sample_every: usize,
    seed: u64,
    drop: f64,
    dup: f64,
    outage_chance: f64,
    outage_min: f64,
    outage_max: f64,
    backlog_rate: usize,
    buffer_cap: usize,
    bad: f64,
    uncertain: f64,
    max_samples: Option<usize>,
    paced: bool,
}

impl Default for Args {
    fn default() -> Self {
        Self {
            speed: 30.0,
            sample_every: 60,
            seed: 20_260_909,
            drop: 0.005,
            dup: 0.01,
            outage_chance: 0.01,
            outage_min: 3.0,
            outage_max: 40.0,
            backlog_rate: 3,
            buffer_cap: 500,
            bad: 0.0005,
            uncertain: 0.002,
            max_samples: None,
            paced: true,
        }
    }
}

fn parse_args() -> Args {
    let mut a = Args::default();
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < argv.len() {
        let flag = argv[i].clone();
        let mut val = || -> String {
            i += 1;
            argv.get(i).cloned().unwrap_or_default()
        };
        match flag.as_str() {
            "--speed" => a.speed = val().parse().unwrap(),
            "--sample-every" => a.sample_every = val().parse().unwrap(),
            "--seed" => a.seed = val().parse().unwrap(),
            "--drop" => a.drop = val().parse().unwrap(),
            "--dup" => a.dup = val().parse().unwrap(),
            "--outage-chance" => a.outage_chance = val().parse().unwrap(),
            "--outage-min" => a.outage_min = val().parse().unwrap(),
            "--outage-max" => a.outage_max = val().parse().unwrap(),
            "--backlog-rate" => a.backlog_rate = val().parse().unwrap(),
            "--buffer" => a.buffer_cap = val().parse().unwrap(),
            "--bad" => a.bad = val().parse().unwrap(),
            "--uncertain" => a.uncertain = val().parse().unwrap(),
            "--max-samples" => a.max_samples = Some(val().parse().unwrap()),
            "--unpaced" => a.paced = false,
            other => panic!("unknown flag {other}"),
        }
        i += 1;
    }
    a
}

struct Metric {
    name: &'static str,
    value: f64,
    status: &'static str,
    source_ms: i64,
}

/// A buffered publish batch. It needs no timestamp of its own: every metric
/// already carries the `sourceTimestamp` it was read at, which is the whole
/// point of a `DataValue` and is what survives being held.
struct Batch {
    metrics: Vec<Metric>,
}

/// Whether the publisher can currently reach the broker.
///
/// A per-message coin flip would scatter late records evenly through the
/// stream, which is not how a link fails. A link goes down, the historian
/// buffers, and everything it buffered arrives at once when the link comes
/// back, so late data arrives in bursts and the worst case a watermark has to
/// tolerate is the length of the outage rather than the average delay.
enum Link {
    Up,
    Down { until_sample: u64 },
}

/// One fault episode: which disturbance, when it starts, when it clears.
fn episode(block: usize, seed: u64) -> (usize, f64, f64) {
    let mut r = rng::Rng::new(seed ^ (block as u64).wrapping_mul(0x1000_0000_1B3));
    let fault = r.pick(&FAULTS);
    let onset = BLOCK_HOURS * block as f64 + r.range(0.5, 7.5);
    let duration = r.range(1.5, 4.0);
    (fault, onset, onset + duration)
}

fn json_escape(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

fn main() {
    let args = parse_args();
    let out = std::io::stdout();
    let mut out = BufWriter::new(out.lock());

    let tags = tags::tags();
    let analyser_indices = tags::analyser_channels();
    let mut is_analyser_channel = vec![false; tags::tags().len()];
    for c in &analyser_indices {
        is_analyser_channel[*c] = true;
    }
    let epoch_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("clock before 1970")
        .as_millis() as i64;

    // The birth certificate: units, descriptions, analyser intervals. Retained
    // on the broker, so a subscriber that joins mid-stream still gets the
    // schema before it gets a value. Sparkplug calls this NBIRTH.
    let mut birth = String::from("{\"type\":\"birth\",\"plant\":\"tep\",\"schema\":\"opcua-datavalue/1\"");
    birth.push_str(&format!(",\"accelerationFactor\":{}", args.speed));
    // The plant keeps its own clock, and it runs `accelerationFactor` times
    // faster than yours. Publishing the epoch means a reader can convert
    // between the two rather than guessing why the timestamps are drifting
    // away from the wall clock at a steady thirty seconds a second.
    birth.push_str(&format!(
        ",\"plantEpoch\":\"{}\"",
        time::rfc3339_millis(epoch_ms)
    ));
    // One integrator step is one second of plant time, so the sample interval
    // in plant seconds is the step count.
    birth.push_str(&format!(",\"sampleIntervalSeconds\":{}", args.sample_every));
    birth.push_str(",\"tags\":[");
    for (k, t) in tags.iter().enumerate() {
        if k > 0 {
            birth.push(',');
        }
        birth.push_str(&format!(
            "{{\"name\":\"{}\",\"description\":\"{}\",\"unit\":\"{}\"",
            json_escape(t.name),
            json_escape(t.description),
            json_escape(t.unit)
        ));
        if let (Some(iv), Some(dt)) = (t.interval_hours, t.dead_time_hours) {
            birth.push_str(&format!(
                ",\"analyserIntervalHours\":{iv},\"deadTimeHours\":{dt}"
            ));
        }
        birth.push('}');
    }
    birth.push_str("]}");
    writeln!(out, "{birth}").unwrap();

    let mut r = rng::Rng::new(args.seed);
    let mut seq: u64 = 0;
    let mut backlog: std::collections::VecDeque<Batch> = std::collections::VecDeque::new();
    let mut link = Link::Up;
    let mut sample_index: u64 = 0;
    let mut overflowed = 0usize;
    let mut hours_offset = 0.0_f64;
    let mut plant_seed = 4_651_207_995.0_f64;
    let mut emitted = 0usize;
    let started = std::time::Instant::now();

    'run: loop {
        let scenario = Scenario::baseline()
            .with_seed(plant_seed)
            .with_hours(100_000.0)
            .sampling_every(args.sample_every);
        let mut sim = Simulation::new(scenario);

        // Analyser channels hold their previous value between due times, so a
        // change is exactly an update and there is no schedule to duplicate
        // here. `last_update_hours` is what makes a held value carry the
        // source time it was actually read at.
        let mut last_value = vec![f64::NAN; tags.len()];
        let mut last_update_hours = vec![0.0_f64; tags.len()];
        let mut active: Option<(usize, f64)> = None;
        let mut block_done = usize::MAX;

        loop {
            if sim.is_halted() {
                break;
            }
            // `step` returns `None` on every step where no sample is due,
            // which is 59 steps out of 60. Termination is `is_halted`, not a
            // `None`, and conflating the two ends the run on the first step.
            let Some(sample) = sim.step() else { continue };
            let hours = sample.hours + hours_offset;

            // Fault schedule, driven from the plant clock rather than from a
            // fixed `Schedule`, which holds only 32 events and would run out
            // after a day and a half.
            let block = (hours / BLOCK_HOURS).floor() as usize;
            let (fault, onset, clears) = episode(block, args.seed);
            if active.is_none() && block_done != block && hours >= onset && hours < clears {
                sim.request_disturbance(fault, true);
                active = Some((fault, clears));
            }
            if let Some((f, until)) = active {
                if hours >= until {
                    sim.request_disturbance(f, false);
                    active = None;
                    block_done = block;
                }
            }

            let row = sample.row();
            let mut metrics = Vec::with_capacity(row.len());
            for (c, &v) in row.iter().enumerate() {
                let is_analyser = is_analyser_channel[c];
                let changed = last_value[c].to_bits() != v.to_bits();
                if is_analyser && changed {
                    last_update_hours[c] = hours;
                } else if !is_analyser {
                    last_update_hours[c] = hours;
                }
                last_value[c] = v;

                let status = if r.chance(args.bad) {
                    "Bad_DeviceFailure"
                } else if r.chance(args.uncertain) {
                    "Uncertain_SensorNotAccurate"
                } else {
                    "Good"
                };
                metrics.push(Metric {
                    name: tags[c].name,
                    value: v,
                    status,
                    source_ms: epoch_ms + (last_update_hours[c] * 3_600_000.0) as i64,
                });
            }

            let now_ms = epoch_ms + (hours * 3_600_000.0) as i64;
            sample_index += 1;

            link = match link {
                Link::Up if r.chance(args.outage_chance) => Link::Down {
                    until_sample: sample_index
                        + r.range(args.outage_min, args.outage_max) as u64,
                },
                Link::Down { until_sample } if sample_index >= until_sample => Link::Up,
                other => other,
            };

            match link {
                Link::Down { .. } => {
                    // The broker is unreachable, so nothing goes out at all.
                    // A bounded buffer is what a real historian has, and when
                    // it fills the oldest records are the ones lost.
                    if backlog.len() >= args.buffer_cap {
                        backlog.pop_front();
                        overflowed += 1;
                    }
                    backlog.push_back(Batch { metrics });
                }
                Link::Up => {
                    if r.chance(args.drop) {
                        // Gone. QoS 0 over a link that dropped it, and nothing
                        // anywhere records that it existed.
                    } else {
                        emit(&mut out, &mut seq, &metrics, now_ms, false);
                        emitted += 1;
                        if r.chance(args.dup) {
                            emit(&mut out, &mut seq, &metrics, now_ms, false);
                            emitted += 1;
                        }
                    }
                    // Backlog drains alongside the live stream rather than in
                    // one burst, because the link that just came back has the
                    // same capacity it always had. This is the interleaving
                    // that puts records out of order.
                    for _ in 0..args.backlog_rate {
                        let Some(b) = backlog.pop_front() else { break };
                        emit(&mut out, &mut seq, &b.metrics, now_ms, true);
                        emitted += 1;
                    }
                }
            }
            out.flush().ok();

            if let Some(max) = args.max_samples {
                if emitted >= max {
                    break 'run;
                }
            }

            if args.paced {
                let due = std::time::Duration::from_secs_f64(hours * 3600.0 / args.speed);
                if let Some(wait) = due.checked_sub(started.elapsed()) {
                    std::thread::sleep(wait);
                }
            }
        }

        // A trip ends the run by default. Restarting is what an operator does,
        // and a historian records the gap rather than pretending the plant
        // never stopped.
        let advanced = sim.hours();
        hours_offset += advanced;
        plant_seed += 1.0;
        assert!(
            advanced > 0.0,
            "the plant halted without advancing; restarting would spin"
        );
        let outcome = sim.outcome();
        writeln!(
            out,
            "{{\"type\":\"event\",\"plant\":\"tep\",\"event\":\"restart\",\"reason\":\"{:?}\",\"timestamp\":\"{}\"}}",
            outcome,
            time::rfc3339_millis(epoch_ms + (hours_offset * 3_600_000.0) as i64)
        )
        .unwrap();
        out.flush().ok();
    }
    out.flush().ok();
    if overflowed > 0 {
        eprintln!("{overflowed} batches lost to buffer overflow");
    }
}

fn emit<W: Write>(
    out: &mut W,
    seq: &mut u64,
    metrics: &[Metric],
    server_ms: i64,
    historical: bool,
) {
    let mut s = String::with_capacity(6144);
    s.push_str("{\"seq\":");
    s.push_str(&(*seq % 256).to_string());
    s.push_str(",\"timestamp\":\"");
    s.push_str(&time::rfc3339_millis(server_ms));
    s.push_str("\",\"isHistorical\":");
    s.push_str(if historical { "true" } else { "false" });
    s.push_str(",\"metrics\":[");
    for (k, m) in metrics.iter().enumerate() {
        if k > 0 {
            s.push(',');
        }
        s.push_str("{\"name\":\"");
        s.push_str(m.name);
        s.push_str("\",\"value\":");
        if m.status.starts_with("Bad") {
            s.push_str("null");
        } else {
            s.push_str(&format!("{:.6}", m.value));
        }
        s.push_str(",\"statusCode\":\"");
        s.push_str(m.status);
        s.push_str("\",\"sourceTimestamp\":\"");
        s.push_str(&time::rfc3339_millis(m.source_ms));
        s.push_str("\"}");
    }
    s.push_str("]}");
    writeln!(out, "{s}").unwrap();
    *seq += 1;
}
