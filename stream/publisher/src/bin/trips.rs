//! Trip rate of the streaming fault schedule over a long run.
#[path = "../rng.rs"]
#[allow(dead_code, reason = "the stream uses more of it than this probe does")]
mod rng;
#[path = "../episode.rs"]
mod episode;
use episode::{episode, BLOCK_HOURS};
use tepsim::{Outcome, Scenario, Simulation};


fn main() {
    let seed: u64 = std::env::args().nth(1).and_then(|s| s.parse().ok()).unwrap_or(20_260_909);
    let target: f64 = std::env::args().nth(2).and_then(|s| s.parse().ok()).unwrap_or(500.0);
    let mut hours_offset = 0.0_f64;
    let mut plant_seed = 4_651_207_995.0_f64;
    let mut trips = 0usize;
    while hours_offset < target {
        let mut sim = Simulation::new(
            Scenario::baseline().with_seed(plant_seed).with_hours(100_000.0).sampling_every(60),
        );
        let mut active: Option<(usize, f64)> = None;
        let mut block_done = usize::MAX;
        let mut last_fault = 0usize;
        while !sim.is_halted() {
            let hours = sim.hours() + hours_offset;
            if hours >= target { break }
            let block = (hours / BLOCK_HOURS).floor() as usize;
            let (fault, onset, clears) = episode(block, seed);
            if active.is_none() && block_done != block && hours >= onset && hours < clears {
                sim.request_disturbance(fault, true);
                active = Some((fault, clears));
                last_fault = fault;
            }
            if let Some((f, until)) = active {
                if hours >= until {
                    sim.request_disturbance(f, false);
                    active = None;
                    block_done = block;
                }
            }
            sim.step();
        }
        if let Some(Outcome::Tripped { hours, cause, .. }) = sim.outcome() {
            trips += 1;
            let abs = hours + hours_offset;
            let (f, on, off) = episode((abs / BLOCK_HOURS).floor() as usize, seed);
            println!(
                "trip at {abs:7.2} h  {cause:?}  block fault IDV({f}) {on:.2}->{off:.2}, last started IDV({last_fault})"
            );
        }
        let advanced = sim.hours();
        if advanced <= 0.0 { println!("no progress, stopping"); break }
        hours_offset += advanced;
        plant_seed += 1.0;
    }
    println!("\n{trips} trips in {hours_offset:.0} plant hours = one per {:.0} h", hours_offset / trips.max(1) as f64);
}
