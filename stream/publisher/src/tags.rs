//! The tag dictionary, built once from the simulator's own variable tables.
//!
//! Every field here comes from `tepsim_core::variables`, which an integration
//! test in that crate checks against the `teprob.f` header comments. Nothing
//! about a tag is retyped here, so a unit cannot drift from the model.

use tepsim::channel_names;
use tepsim_core::variables::{MANIPULATED, MEASUREMENTS};

pub struct Tag {
    pub name: &'static str,
    pub description: &'static str,
    pub unit: &'static str,
    /// Analyser sampling interval in plant hours, for the 19 sampled
    /// compositions. `None` for a continuous instrument or a valve.
    pub interval_hours: Option<f64>,
    pub dead_time_hours: Option<f64>,
}

pub fn tags() -> Vec<Tag> {
    let names = channel_names();
    let mut out = Vec::with_capacity(names.len());
    for (i, info) in MEASUREMENTS.iter().enumerate() {
        out.push(Tag {
            name: names[i],
            description: info.description,
            unit: info.unit.fortran_spelling(),
            interval_hours: info.analyzer.map(|a| a.sampling_interval_hours()),
            dead_time_hours: info.analyzer.map(|a| a.dead_time_hours()),
        });
    }
    for (j, info) in MANIPULATED.iter().enumerate() {
        out.push(Tag {
            name: names[MEASUREMENTS.len() + j],
            description: info.description,
            unit: "%",
            interval_hours: None,
            dead_time_hours: None,
        });
    }
    out
}

/// Zero-based channel indices of the sampled composition analysers.
pub fn analyser_channels() -> Vec<usize> {
    MEASUREMENTS
        .iter()
        .enumerate()
        .filter(|(_, m)| m.analyzer.is_some())
        .map(|(i, _)| i)
        .collect()
}
