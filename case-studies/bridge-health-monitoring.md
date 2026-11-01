# Case study · Separating temperature from damage on the Z24 bridge

:::{admonition} At a glance
:class: tip
- **Field**: Civil and environmental engineering, structural health monitoring
- **Connects to**: [L1 · The AI-engineering landscape](../lectures/l01/notes.md), [L6 · Streaming concepts and data validation](../lectures/l06/notes.md), [L8 · The machine learning workflow I, time series](../lectures/l08/notes.md)
- **Primary source**: Peeters and De Roeck (2001), *Earthquake Engineering and Structural Dynamics*; with the KU Leuven Z24 benchmark description
:::

## Why this matters

Structural health monitoring rests on a simple physical idea. A bridge vibrates at natural frequencies set by its stiffness and its mass, and damage such as cracking or a failed support lowers the stiffness. If you track the natural frequencies continuously, a drop should tell you the structure has lost stiffness somewhere, long before an inspector would see it.

The difficulty is that stiffness also changes for reasons that have nothing to do with damage. Concrete, asphalt, bearings, and the soil around foundations all respond to temperature. A monitoring system that alarms on every frequency shift will alarm every cold night, and operators will learn to ignore it. One that ignores the shifts will miss the damage it was installed to find.

The Z24 bridge in Switzerland is the best-documented test of this problem. It was monitored for most of a year, and then deliberately and progressively damaged before demolition, so the data contain both a full cycle of seasons and known damage events. The question it answers is concrete: can you tell the difference, and what does it take?

## The setting

The Z24 was a post-tensioned concrete box-girder road bridge near Solothurn in the canton of Bern, carrying the road between Koppigen and Utzenstorf over the A1 motorway between Bern and Zürich. According to the [KU Leuven benchmark page](https://bwk.kuleuven.be/bwm/z24), it had a 30 m main span and two 14 m side spans. It dated from 1963 and was demolished at the end of 1998 to make room for a new railway. Monitoring and damage tests ran under the European project SIMCES (System Identification to Monitor Civil Engineering Structures), coordinated by KU Leuven.

The long-term monitoring ran during the year before demolition. Its stated aim was to quantify how much the environment moves the bridge dynamics, so the instrumentation was weighted heavily toward the weather and the bridge's thermal state. Sensors recorded air temperature, humidity, rain, wind speed and direction, and the presence of vehicles. Temperature was measured at eight points across the girder cross-section at the middle of each span, and in the soil near the supports. Sixteen accelerometers recorded the vibration. Every hour the system stored 10 scans of 48 environmental channels and 8 averages of 8192 acceleration samples from the 16 accelerometers.

Two details on the benchmark page matter for anyone using the data. The original blueprints showed a 5 cm asphalt layer, but drilling the holes for the temperature sensors revealed 16 to 18 cm, so the team added pavement temperature sensors. And the monitoring hardware degraded. Construction of the replacement bridge destroyed six temperature sensors and damaged an accelerometer. Some accelerometers drifted considerably or failed, although they were a type designed for long-term use.

From the hourly acceleration records, the researchers identified the natural frequencies of the bridge, the quantity tracked through the year. A later analysis by [Langone et al. (2017)](https://lirias.kuleuven.be/retrieve/9d8e7804-e066-4df4-9199-3b437beac335) describes the resulting dataset as four natural frequencies over 5652 samples.

The progressive damage test followed in August and September 1998. The benchmark page lists the scenarios with the date each was fully realized. They began with an undamaged reference on 4 August, lowered one pier in steps of 20, 40, 80 and 95 mm, and then lifted it back. Later scenarios spalled concrete from the soffit, failed a concrete hinge and several anchor heads, and finally cut 2, 4 and then 6 of the 16 prestressing tendons on 7 to 9 September.

## What happened

The central result, stated in the [abstract of Peeters and De Roeck (2001)](https://doi.org/10.1002/1096-9845(200102)30:2%3C149::AID-EQE1%3E3.0.CO;2-Z), is that environmental conditions change the bridge's natural frequencies, and that temperature is the most important of them. Temperature can act through two routes: the material properties and the boundary conditions. The authors frame the task as separating these normal changes from abnormal ones caused by a loss of stiffness, because a normal change should not raise an alarm.

The effect of cold was the largest and least tidy part. Nguyen et al. (2017) replotted the first natural frequency of the Z24 against surface temperature, in [an open preprint](https://orbilu.uni.lu/bitstream/10993/31453/1/PrePrint.pdf) comparing several bridges. They found the relation could be approximated as linear between 0 and 40 °C, with a slope of about 1‰ per °C and a ±3σ scatter band of about 2.5%. Over that 40 °C range the slope alone amounts to roughly 4% of the frequency. Below 0 °C the relation breaks: the structure stiffens sharply, which the authors attribute to freezing. Langone et al. (2017) describe the same feature in February 1998. The temperature fell below zero, and a rapid increase in the Young's modulus of the asphalt layer produced a peak in all of the vibration modes.

The environmental swing is larger than the early damage. Gowdridge, Dervilis and Worden ([arXiv:2209.05484](https://arxiv.org/abs/2209.05484)) report air temperatures from −9 °C to 36 °C over the campaign, and find that temperature moved the natural frequencies more than the introduced damage did. They conclude, as Peeters and De Roeck did, that the size of a frequency change says little about whether damage is present.

Peeters and De Roeck therefore did not threshold the raw frequencies. They fitted black-box models to the healthy-bridge data that predict each natural frequency from temperature, and compared each new measurement with the model's prediction. A measured frequency outside the model's confidence intervals has, in their words from the abstract, "probably another cause than the temperature", for instance damage. As summarized by Langone et al., the model was an autoregressive model with exogenous inputs (ARX), with temperature as the input. It flagged the second, third and fourth natural frequencies on 7 and 8 August 1998 and the first on 15 August, shortly after the progressive damage test began.

Later work shows how sensitive detection is to what counts as normal. Langone et al. trained an unsupervised clustering detector on about the first month of monitoring. It raised a false alarm on 3 February 1998, during the freeze, and then caught the damage on 7 August. Trained on about three months that included the winter, it raised no false alarm, but detected the damage later. A standard fuzzy C-means clustering of the same four frequencies never detected the damage at all.

## Why it happened

The mechanism is physical. A natural frequency depends on stiffness, and the stiffness of a concrete and asphalt deck depends on temperature. Above freezing the dependence is mild and close to linear. Below freezing the asphalt, much thicker on this bridge than the drawings said, becomes far stiffer (Langone et al.), and Nguyen et al. point to freezing changing the stiffness of the structure or its bearing conditions. Either way, the cold adds stiffness that the warm-weather relation does not predict.

In the course's terms, the natural frequency is a measured quantity driven by two causes at once: the structural condition you care about and a confounding environmental input you do not. The healthy bridge does not have one frequency. It has a frequency that is a function of temperature, and the damage signal is the departure from that function. A raw frequency threshold mixes the two and fails both ways. Set it wide enough to tolerate a freeze and it misses a lowered pier; set it narrow and it alarms every cold night.

The fix is to model the confounder explicitly, then detect on the residual. That model has to be trained on data spanning the conditions it will meet, since a model that has never seen a freeze treats the freeze as damage. Training on data that include the freeze widens the idea of normal, which costs sensitivity to small damage.

## Connections to the lectures

The section on why engineering data is different in [L1](../lectures/l01/notes.md) measures how a gas-sensor calibration fitted on spring data degrades through the year. The error swings with the season instead of creeping upward, because the model "learned spring". A damage indicator fitted on a few months of the Z24 is partly a thermometer in the same way. The benchmark page also reports accelerometers that drifted and sensors lost to construction, which is the sensor drift L1 describes, in a project built to avoid it. The asphalt layer, more than three times thicker than the drawings, is the L1 dataset note in another field: the documentation and the artifact disagreed, and only measuring revealed it. Two widely used processed versions of the frequency data also differ in length: 5652 samples in Langone et al., and 3932 observations in [Hughes et al., arXiv:2201.02555](https://arxiv.org/abs/2201.02555). The provenance of the version you download matters.

The section on data validation in [L6](../lectures/l06/notes.md) separates physical-plausibility checks from statistical checks, and the limitations section warns that validation confirms plausibility, not correctness. The Z24 shows the converse case. A frequency during the February freeze is physically real, yet it looks anomalous to a statistical check calibrated on the first month. L6 also asks what a failed check should do: block, warn, or quarantine. For a bridge, blocking means closing a road, so a check that fails on every freeze cannot be allowed to block.

The section on residuals as diagnosis and detection in [L8](../lectures/l08/notes.md) is the method Peeters and De Roeck used. L8 builds a detector in three steps: fit a model on normal operation, set a threshold from residuals on held-out normal data, and alarm when a new residual exceeds it. The ARX model of frequency against temperature is that model, and the confidence interval is that threshold. L8 also states that the false-alarm rate and the detection delay trade against each other. The two Langone runs show the trade directly: the one-month training set gave an early detection and a false alarm, and the three-month set gave no false alarm and a later detection. The algorithm was the same in both; only the span declared normal changed.

:::{admonition} What a practitioner should take from this
:class: note
- Do not threshold a raw physical feature that a known environmental input also moves. Model the feature as a function of the input on healthy data, and detect on the residual.
- Train the normal model on at least one full cycle of the environment it will see, including the extremes. A model fitted on one season will raise its first false alarm in the next.
- Look for regime changes such as freezing, and do not force one linear relation across them. A linear temperature model was a reasonable fit above 0 °C on the Z24 and a poor one below it.
- Instrument the confounder as carefully as the response. The Z24 team placed more temperature sensors than accelerometers, and found the asphalt thickness only because they drilled for those sensors.
- Report a detector's false-alarm rate and detection delay together, measured on held-out normal data and on known damage. Either number alone hides the trade.
:::

## Sources

- [Peeters and De Roeck, "One-year monitoring of the Z24-Bridge: environmental effects versus damage events", *Earthquake Engineering and Structural Dynamics* 30(2): 149 to 171 (2001)](https://doi.org/10.1002/1096-9845(200102)30:2%3C149::AID-EQE1%3E3.0.CO;2-Z). The primary source for the temperature model and its confidence intervals; paywalled, and we could not reach an author copy, so this page cites it only for what its abstract states and relies on the sources below for detail.
- [KU Leuven Structural Mechanics, "Z24 Bridge benchmark"](https://bwk.kuleuven.be/bwm/z24). The research group's own description of the bridge, the sensors, the hourly acquisition, the sensor losses, and the dated table of damage scenarios; the data are available there on registration for non-commercial research.
- [Langone, Reynders, Mehrkanoon and Suykens, "Automated structural health monitoring based on adaptive kernel spectral clustering", *Mechanical Systems and Signal Processing* 90: 64 to 78 (2017)](https://lirias.kuleuven.be/retrieve/9d8e7804-e066-4df4-9199-3b437beac335). Author manuscript on KU Leuven's Lirias repository ([doi:10.1016/j.ymssp.2016.12.002](https://doi.org/10.1016/j.ymssp.2016.12.002)); the source for the ARX detection dates, the February freeze, and the one-month versus three-month training comparison.
- [Nguyen, Mahowald, Schommer, Maas and Zuerbes, "A study of temperature and aging effects on eigenfrequencies of concrete bridges for health monitoring", *Engineering* 9(5): 396 to 411 (2017)](https://orbilu.uni.lu/bitstream/10993/31453/1/PrePrint.pdf). Author preprint on the University of Luxembourg repository ([doi:10.4236/eng.2017.95023](https://doi.org/10.4236/eng.2017.95023)); compares frequency against temperature for three bridges, including the Z24, and shows how much slope and scatter vary between structures.
- [Gowdridge, Dervilis and Worden, "On the application of topological data analysis: a Z24 Bridge case study", arXiv:2209.05484](https://arxiv.org/abs/2209.05484). Open preprint; the source for the recorded temperature range and the estimate of temperature versus damage effects, which it states without derivation.
- [Hughes, Bull, Gardner, Dervilis and Worden, "On robust risk-based active-learning algorithms for enhanced decision support", arXiv:2201.02555](https://arxiv.org/abs/2201.02555). Open preprint that uses the Z24 frequencies as a four-class problem with a separate cold-temperature class, a useful example of labelling the confounder rather than ignoring it.
