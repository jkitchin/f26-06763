//! Prints the fault schedule the stream will run, so it can be read before it
//! is streamed.
#[path = "../rng.rs"]
#[allow(dead_code, reason = "the stream uses more of it than this probe does")]
mod rng;

const BLOCK_HOURS: f64 = 12.0;
const FAULTS: [usize; 14] = [1, 2, 4, 5, 7, 8, 10, 11, 12, 13, 14, 17, 18, 20];

fn main() {
    let seed: u64 = std::env::args()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(20_260_909);
    let blocks: usize = std::env::args()
        .nth(2)
        .and_then(|s| s.parse().ok())
        .unwrap_or(8);
    for block in 0..blocks {
        let mut r = rng::Rng::new(seed ^ (block as u64).wrapping_mul(0x1000_0000_1B3));
        let fault = r.pick(&FAULTS);
        let onset = BLOCK_HOURS * block as f64 + r.range(0.5, 7.5);
        let duration = r.range(1.5, 4.0);
        println!(
            "block {block:2}  IDV({fault:2})  {onset:7.2} h -> {:7.2} h  ({duration:.2} h)",
            onset + duration
        );
    }
}
