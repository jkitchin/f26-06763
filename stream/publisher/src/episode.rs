//! The fault schedule, shared by the stream and by the tools that inspect it.
//!
//! This lives in one file because it was briefly in three, and the copy in
//! `bin/schedule.rs` went stale: it kept printing IDV(7) episodes for a stream
//! that no longer runs them, so the tool that exists to say what the plant will
//! do was the one thing describing a plant that does not exist.

/// Plant hours between fault episodes. Exactly one onset per block, so any
/// window this long contains at least one, whenever a student happens to run.
/// At 144x that is five wall-clock minutes, so the ten-minute collection the
/// assignment asks for spans two episodes wherever in the day it starts.
pub const BLOCK_HOURS: f64 = 12.0;

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
pub const FAULTS: [usize; 13] = [1, 2, 4, 5, 8, 10, 11, 12, 13, 14, 17, 18, 20];

/// One fault episode: which disturbance, when it starts, when it clears.
pub fn episode(block: usize, seed: u64) -> (usize, f64, f64) {
    let mut r = crate::rng::Rng::new(seed ^ (block as u64).wrapping_mul(0x1000_0000_1B3));
    let fault = r.pick(&FAULTS);
    let onset = BLOCK_HOURS * block as f64 + r.range(0.5, 7.5);
    let duration = r.range(1.5, 4.0);
    (fault, onset, onset + duration)
}
