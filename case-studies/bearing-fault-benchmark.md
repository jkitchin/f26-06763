# Case study · Near-perfect bearing fault classifiers on the CWRU benchmark

:::{admonition} At a glance
:class: tip
- **Field**: Mechanical and electrical engineering, machine condition monitoring
- **Connects to**: [L7 · Features for time-series models](../lectures/l07/notes.md), [L10 · Classification](../lectures/l10/notes.md), [L12 · Architectures for engineering data](../lectures/l12/notes.md)
- **Primary source**: Smith and Randall (2015), *Mechanical Systems and Signal Processing*; with Vieira, Bauler, Rosa and Silva (2026), *Mechanical Systems and Signal Processing*
:::

## Why this matters

Rolling element bearings sit in nearly every motor, pump, fan, and gearbox, and a worn bearing is one of the most common reasons a rotating machine stops. Vibration analysis is a well-developed way to catch one early. An accelerometer on the bearing housing picks up the small impacts that a crack or pit makes each time a ball rolls over it, and a trained analyst can read the fault from the spectrum.

Data from the Case Western Reserve University (CWRU) Bearing Data Center became the standard reference for testing new diagnostic algorithms in the decade before 2015, as Smith and Randall noted that year. A 2026 study in *Mechanical Systems and Signal Processing* sampled 18 bearing fault papers published in 2025. The nine that used CWRU reported scores ranging from above 94% up to 100%. On the face of it, bearing fault classification looks solved.

Two lines of work say it is not. In 2015 two vibration specialists diagnosed every CWRU record with established signal processing. Relatively few records showed the classic symptoms of their labeled fault, and some showed no diagnosable fault at all. Later studies showed that the standard ways of splitting CWRU into training and test sets put the same physical bearing on both sides. When the split is done by bearing, the same deep networks fall from near-perfect scores to roughly halfway between perfect and a coin flip. Anyone who trains a classifier on recordings from a small number of test articles (bearings, specimens, patients, sensors) can make the same mistake.

## The setting

The CWRU test stand is a 2 hp electric motor driving a dynamometer through a torque transducer, according to the [Bearing Data Center's description of the apparatus](https://engineering.case.edu/bearingdatacenter/apparatus-and-procedures). Single-point faults were cut into test bearings by electro-discharge machining, with diameters of 7, 14, 21, 28, and 40 mils (thousandths of an inch). Each faulted bearing was installed at either the drive end or the fan end of the motor. Accelerometers on the motor housing recorded vibration at 12,000 samples per second, and at 48,000 samples per second for some drive-end faults.

Smith and Randall's paper adds the details that matter for machine learning. Each faulty bearing was reinstalled and run at four motor loads, 0 to 3 hp, which move the shaft speed between about 1797 and 1720 rpm. They catalog 161 data sets in all. They also point out that "load" is close to meaningless for the bearing itself: nothing on the rig turns the motor torque into a radial load on the bearing, so the main effect of load is a shaft speed drop of almost 4%.

The consequence is a dataset with very few physical objects in it. Vieira and colleagues describe it as a single pair of healthy bearings plus a set of faulty bearings, each recorded at four loads, with each recording about 10 seconds long. One bearing with one fault produces four recordings that differ mainly in shaft speed. A typical pipeline then cuts each 10-second recording into many short windows, and those windows become the samples a classifier sees.

## What happened

### The labels do not always match the signal

Smith and Randall applied three established diagnostic methods to the whole dataset: envelope analysis of the raw signal, envelope analysis after cepstrum prewhitening, and a more involved benchmark method using spectral kurtosis. Envelope analysis looks for the rate at which fault impacts repeat, which bearing geometry and shaft speed fix in advance for each fault type. They sorted every record into six categories, from Y1 (clearly diagnosable with classic symptoms) through P1 and P2 (partially diagnosable) to N1 and N2 (not diagnosable).

The results ranged from records that simple envelope analysis diagnosed at once to records that no method could diagnose. Their conclusions state that "relatively few of the records gave classical characteristics for the specified bearing fault type." Ball faults were the hardest; in the 12 kHz drive-end set, only the 21-mil and 28-mil ball faults were diagnosable by envelope analysis of the raw signal. Their Table 6 lists the records not diagnosable by any method. It includes all four 28-mil inner race records at the drive end (records 3001 to 3004) and every one of the four 7-mil drive-end ball fault records, at one or more measurement points.

They also found a pattern that matters directly for classification. The diagnosis outcomes, they wrote, "seem to be less a function of the fault size or speed/load and more a function of the assembly." The rig was rebuilt each time a new bearing went in, and they attribute the variation to mechanical looseness whose severity changed with each installation. In their words, "the test rig assembly seemed to affect the diagnosis results more than the fault itself."

### The splits put one bearing on both sides

Vieira, Bauler, Rosa and Silva (2026) measured how much the split changes the score. They trained a wide first-layer kernel convolutional network (WDCNN), a 1D CNN commonly used on vibration signals, on one group of drive-end recordings: one load and one fault size, three signals in all. They then tested the same trained model three ways. The metric was macro AUROC, the area under the ROC curve averaged over the inner race, outer race, and ball detectors, where 100% is perfect and 50% is a coin flip.

| How the test set was chosen | Macro AUROC, time-domain input |
|---|---|
| Same recordings, last 20% of each signal held out | 100.00% ± 0.00% |
| Same bearings, other motor loads | 100.00% ± 0.00% |
| Different bearings (other fault sizes) | 63.17% ± 10.84% |

The frequency-domain and envelope-spectrum inputs followed the same pattern, scoring 99.79% to 100% on the two leaky splits and 63% to 64% on the bearing-wise split (their Table 13). For one model trained on the 0 hp, 7-mil group, the per-fault AUROC on unseen bearings was 94.8% for inner race, 53.9% for outer race, and 78.7% for ball faults, against a perfect score under the leaky split.

Earlier work had reached the same conclusion with different splits. Hendriks, Dumond and Knox (2022) split CWRU by fault size, which keeps each faulty bearing on one side. As summarized by Rosa, Braga and Silva (2024), deep convolutional networks that scored 95% accuracy on the split by load scored 53% on the split by fault size.

### A tree on spectral features beat the network

With the bearing-wise split in place, Vieira and colleagues compared the network with classical models on handcrafted features. A random forest on time-domain and envelope-spectrum features reached a macro AUROC of 85.06% ± 8.92%. The best WDCNN, on envelope-spectrum input, reached 74.51% ± 9.43%, and on raw time-domain input 63.22%. Even the random forest is far from a deployable detector: at a 90% detection rate, its false positive rates were 27% for inner race, 42% for outer race, and 35% for ball faults.

## Why it happened

The evidence points to the model learning which bearing it was listening to. Each physical bearing, once installed, carries its own signature: its fault, but also the mechanical looseness of that installation, which Smith and Randall found changed each time the rig was rebuilt. Every window cut from that recording shares the signature. When training and test windows come from the same recording, or the same bearing at a different load, the classifier can score perfectly by recognizing the installation. It never has to learn what an inner race fault sounds like on a bearing it has not met.

Vieira and colleagues name two mechanisms. Segmentation-level leakage puts segments of one continuous recording on both sides of the split. It happens even when the segments do not overlap and even when the held-out part comes later in time, because the whole recording is physically coherent. Bearing-level leakage puts recordings of one bearing on both sides, which is what a split by motor load does on CWRU.

Smith and Randall's findings help explain why the leaky score can be perfect while the honest one is so much lower. If assembly dominates the signal and few records show classic symptoms of their labeled fault, then the installation is likely the strongest feature in the data, and a flexible model will find it first. The labels are correct, since each bearing really had that fault, but a recording does not always carry clear evidence of it.

## Connections to the lectures

The section on data leakage in [Lecture 7](../lectures/l07/notes.md) separates target leakage from train-test contamination and gives the fix for time series as "split on time, not at random." CWRU shows the limit of that fix. Holding out the last 20% of each recording respects time order and still scored 100%. The relevant idea is the group key from that lecture's "Record boundaries and the group key" section: the rows of a log are separate experiments, and the split has to respect what identifies one. For CWRU the experiment is the installed bearing, so the group key is the bearing, and load is not part of it.

[Lecture 10](../lectures/l10/notes.md) explains, in "Why accuracy is not enough," that accuracy hides the difference between a missed fault and a false alarm. CWRU adds two more reasons. With one healthy bearing pair against many faulty ones, the classes are lopsided toward faults, which is the reverse of a real plant. And the AUROC used by Vieira and colleagues is a summary of the curve traced out in "Moving the threshold," which is why they report false positive rates at a fixed detection rate. The section "Faults the classifier never saw" makes the related point that a classifier only recognizes what resembles its training data. On CWRU, a new bearing with a familiar fault type already counts as unfamiliar.

The section "Does the architecture earn its keep?" in [Lecture 12](../lectures/l12/notes.md) found that a gradient-boosted tree on window summaries did slightly better than a 1D CNN on engine sensor data, within the fold-to-fold noise, under a split grouped by engine. The bearing results repeat that finding on vibration data: under a bearing-wise split, a random forest on envelope-spectrum features beat the WDCNN by about ten points of macro AUROC. Lecture 12's limitations section warns that deep networks need more data than engineering datasets often have. The part of CWRU that Vieira and colleagues used holds 144 signals but only 20 bearings, 18 of them faulty. They found that the number of distinct training bearings, more than the number of windows, drove how well a model generalized.

:::{admonition} What a practitioner should take from this
:class: note
- Before splitting, write down what one independent unit is in your data: a bearing installation, a specimen, a patient, a turbine. Split by that unit, and put every window from it on one side.
- Treat "operating condition" splits with suspicion. If the same physical object appears at several loads or speeds, a split by load is a split within one object.
- Run the leaky split and the grouped split on the same model and report both. A large gap measures how much the model relies on recognizing the unit.
- Check whether the signal shows the labeled fault at all. Envelope analysis is a cheap physics check, and records that fail it are a warning about what a classifier can learn from them.
- Benchmark a classical model on envelope-spectrum features before claiming a deep network helps, and report false alarm rates at a fixed detection rate rather than accuracy.
:::

## Sources

- [Smith and Randall, "Rolling element bearing diagnostics using the Case Western Reserve University data: A benchmark study", *Mechanical Systems and Signal Processing* 64 to 65: 100 to 131 (2015)](https://doi.org/10.1016/j.ymssp.2015.04.021). The record-by-record diagnosis of the whole dataset, with the Y/P/N categories and the list of undiagnosable records; paywalled, and we could not find an author copy.
- [Vieira, Bauler, Rosa and Silva, "Towards a more realistic evaluation of machine learning models for bearing fault diagnosis", arXiv:2509.22267](https://arxiv.org/abs/2509.22267). Author preprint (v5) of the 2026 *MSSP* article ([doi:10.1016/j.ymssp.2026.114640](https://doi.org/10.1016/j.ymssp.2026.114640)); the source for the leakage experiment, the random forest comparison, and the survey of 2025 papers.
- [Case Western Reserve University Bearing Data Center](https://engineering.case.edu/bearingdatacenter). The dataset itself; the apparatus and procedures page gives the rig, fault sizes, sensor placement, and sampling rates.
- [Rosa, Braga and Silva, "Benchmarking deep learning models for bearing fault diagnosis using the CWRU dataset: A multi-label approach", arXiv:2407.14625 (2024)](https://arxiv.org/abs/2407.14625). An open preprint that reviews the earlier leakage studies and reformulates CWRU as one binary detector per fault type; useful for its account of why the single healthy bearing pair makes a fully clean multi-class split impossible.
- [Hendriks, Dumond and Knox, "Towards better benchmarking using the CWRU bearing fault dataset", *Mechanical Systems and Signal Processing* 169: 108732 (2022)](https://doi.org/10.1016/j.ymssp.2021.108732). The fault-size split; paywalled, so the 95% and 53% figures on this page are as reported by Rosa et al.
