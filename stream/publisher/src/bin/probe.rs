//! Which disturbances a continuously running plant survives being switched
//! on and then off again.
//!
//! Switching one off is the part that matters and the part a fault-detection
//! benchmark never tests: the published TEP datasets start a fault and run to
//! the end of the file, so nothing in them exercises the recovery. A plant
//! that rides out IDV(7) for four hours can still trip on reactor pressure
//! half an hour after it clears.
use tepsim::{Outcome, Scenario, Simulation};

fn main() {
    let durations = [1.5_f64, 2.5, 4.0];
    println!("        {:>12} {:>12} {:>12}", "1.5 h", "2.5 h", "4.0 h");
    for fault in 1..=20 {
        print!("IDV({fault:2}) ");
        for d in durations {
            let mut sim = Simulation::new(Scenario::baseline().with_hours(16.0).sampling_every(60));
            let (mut on, mut off) = (false, false);
            while !sim.is_halted() {
                let h = sim.hours();
                if !on && h >= 1.0 {
                    sim.request_disturbance(fault, true);
                    on = true;
                }
                if on && !off && h >= 1.0 + d {
                    sim.request_disturbance(fault, false);
                    off = true;
                }
                sim.step();
            }
            match sim.outcome() {
                Some(Outcome::Tripped { hours, .. }) => print!("{:>12}", format!("trip {hours:.1}h")),
                Some(Outcome::SolveFailed { .. }) => print!("{:>12}", "solve fail"),
                _ => print!("{:>12}", "ok"),
            }
        }
        println!();
    }
}
