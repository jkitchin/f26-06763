//! Prints the fault schedule the stream will run, so it can be read before it
//! is streamed.
#[path = "../rng.rs"]
#[allow(dead_code, reason = "the stream uses more of it than this probe does")]
mod rng;
#[path = "../episode.rs"]
mod episode;
use episode::episode;

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
        let (fault, onset, clears) = episode(block, seed);
        println!(
            "block {block:2}  IDV({fault:2})  {onset:7.2} h -> {clears:7.2} h  ({:.2} h)",
            clears - onset
        );
    }
}
