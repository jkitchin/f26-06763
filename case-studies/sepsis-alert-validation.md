# Case study · Validating a deployed sepsis alert

:::{admonition} At a glance
:class: tip
- **Field**: Health care analytics and health information systems
- **Connects to**: [L1 · The AI-engineering landscape](../lectures/l01/notes.md), [L10 · Classification and experiment tracking](../lectures/l10/notes.md), [L14 · Uncertainty quantification in machine learning](../lectures/l14/notes.md)
- **Primary source**: Wong et al. (2021), *JAMA Internal Medicine* 181(8):1065-1070
:::

## Why this matters

A classifier that ships inside a widely used software product reaches many hospitals before any of them has measured it on their own patients. The Epic Sepsis Model (ESM) is a proprietary model that ran inside Epic's electronic health record (EHR) software. According to the study this page follows, it was implemented at hundreds of US hospitals, while little information about its performance was publicly available.

In 2021 a team at Michigan Medicine, the academic health system of the University of Michigan, published an external validation of the ESM on their own hospitalized patients. They found that it discriminated poorly between patients who did and did not develop sepsis. At the alert threshold the hospital used, it missed two thirds of sepsis cases. It also raised an alert for nearly one hospitalization in five. The developer's own reported discrimination was substantially higher.

The study is useful here because every number in it maps onto a quantity defined in the lectures: recall, precision, the base rate, the decision threshold, calibration. It also shows a choice that the textbook formulas leave open. The authors had to decide what the right unit of evaluation was, and what the model should be compared against. Those two choices changed the answer more than any tuning would have.

## The setting

Hospitals want to detect sepsis early so that antibiotics can start promptly, and the study uses timely antibiotics as its measure of usual care. The ESM is a penalized logistic regression, developed by Epic Systems Corporation on data routinely recorded in the EHR. The paper reports that Epic developed and validated it on data from 405,000 patient encounters. Inside a hospital it recomputes a score for each patient every 15 minutes, and the hospital chooses the score above which clinicians are notified.

The Michigan team ran a retrospective cohort study of 27,697 adult patients with 38,455 hospitalizations between December 6, 2018 and October 20, 2019. They used the ESM scores that had been computed prospectively, every 15 minutes, during those stays. The model was used to generate alerts on two hospital units starting March 11, 2019. A hospital operations committee had chosen a score of 6 or higher to page clinicians, which the paper notes falls within the range of 5 to 8 suggested by the developer.

The outcome needed a definition that did not depend on the model. The authors defined sepsis as meeting either of two criteria. The first was the Centers for Disease Control and Prevention surveillance definition. The second was an ICD-10 sepsis diagnosis code together with two systemic inflammatory response syndrome criteria and one organ dysfunction criterion, all within 6 hours of one another. By this definition, sepsis occurred in 2,552 of the 38,455 hospitalizations, or 7%.

To measure what the model added beyond normal practice, the authors also recorded whether each sepsis patient received timely antibiotics, meaning antibiotics given before or within 3 hours after sepsis onset. A patient who was already being treated is a case the clinicians had caught, whatever the model said.

## What happened

The headline discrimination result was a hospitalization-level area under the receiver operating characteristic curve (AUC) of 0.63 (95% CI, 0.62 to 0.64). The AUC is the probability that a randomly chosen positive case receives a higher score than a randomly chosen negative case, so 0.5 is a coin flip and 1.0 is perfect ranking. The paper contrasts its 0.63 with the 0.76 to 0.83 that Epic reported in internal documentation that was shared with the authors with permission. It also cites 0.73 from a conference proceeding coauthored with Epic.

At the threshold of 6, the paper reports a hospitalization-level sensitivity of 33%, specificity of 83%, positive predictive value (PPV) of 12%, and negative predictive value of 95%. In counts, a score of 6 or higher occurred in 6,971 of the 38,455 hospitalizations (18%), even without counting repeated alerts for the same patient. The ESM did not identify 1,709 of the 2,552 patients with sepsis (67%).

The comparison with usual care is the result the authors emphasize. Of the 2,552 hospitalizations with sepsis, the ESM flagged 183 (7%) that had not received timely antibiotics. Those 183 are the cases where the alert could have told clinicians something they had not already acted on. Of the 1,709 sepsis patients the model missed, 1,030 (60%) still received timely antibiotics from their clinicians.

The authors also expressed the alert burden as a number needed to evaluate. If each patient is alerted only once, at the first score of 6 or higher, clinicians would need to evaluate 8 patients to find one who eventually developed sepsis. If clinicians respond to every time a score crosses 6, trying to catch sepsis within the next 4 hours, that figure becomes 109 patients.

Calibration was also poor. The authors report it was poor at all time horizons the developer might have considered, using calibration plots of rescaled scores against observed risk, which appear in the paper's supplement. Their conclusion is that the ESM had poor discrimination and calibration in predicting sepsis onset. They also state that its widespread adoption despite poor performance raises fundamental concerns about sepsis management nationally. The paper notes that this was a single academic medical center, so the result describes this model at this site.

## Why it happened

Three features of the evaluation explain most of the gap between the developer's numbers and the Michigan numbers. None of them requires the model to have changed.

The first is the unit of evaluation. The model emits a score every 15 minutes, so there are many predictions per hospitalization. The authors also computed AUCs at prediction horizons of 4 to 24 hours, treating each prediction as an independent case, and got 0.72 to 0.76. They argue those figures mislead, because a patient who is not septic contributes dozens of correctly low scores and only a few high ones. Those few high scores barely move a per-prediction AUC, but each one is an alert that a nurse or physician must answer. The hospitalization-level AUC of 0.63 judges the whole trajectory, which matches how the alert is experienced.

The second is timing. When the authors included scores generated up to 3 hours after sepsis onset, the hospitalization-level AUC rose to 0.80 (95% CI, 0.79 to 0.81). A score computed after onset is easier to get right, because the signs of sepsis are already in the record. The authors read this as evidence that many alerts reflect sepsis already apparent to clinicians, citing an earlier study in which alerts came a median of 7 hours after the first lactate measurement. An evaluation that counts late predictions as successes measures recognition, while the clinical purpose is anticipation.

The third is the base rate. With sepsis in about 7% of hospitalizations, even a moderate false-positive rate swamps the true alerts. The paper's own figures are consistent with this. Subtracting the 1,709 missed cases from 2,552 leaves 843 sepsis hospitalizations flagged, out of 6,971 flagged in total, which is the 12% PPV. One alert in eight was a true case, and that is where the number needed to evaluate of 8 comes from.

## Connections to the lectures

The section on validation in [L1](../lectures/l01/notes.md), "Validating well is not evidence that a system works", describes Google Flu Trends, a model with strong held-out results that failed in deployment. The ESM case has the same structure in a different form. The developer's validation was internal, and the external result was substantially lower. L1's practitioner advice was to keep a simple, honest baseline and compare against it continuously. Wong et al. chose usual care as that baseline, by asking which septic patients had not already received timely antibiotics. Against that baseline the model's contribution was 183 of 2,552 cases, a number no AUC reports.

The section "Measuring a classifier" in [L10](../lectures/l10/notes.md) supplies the vocabulary. Sensitivity is L10's recall, and PPV is its precision. L10's "Why accuracy is not enough" shows a do-nothing detector scoring 85.4% accuracy on a plant where 85.4% of samples are normal. Here the imbalance is stronger, with 93% of hospitalizations not septic, so the negative predictive value of 95% sounds reassuring while recall is 33%. L10's "Moving the threshold" says to choose the threshold from the cost of a miss against the cost of a false alarm. At Michigan that trade-off was set by a committee at a score of 6, and the number needed to evaluate is the cost of a false alarm expressed in clinician time. The AUC itself is a summary over all thresholds, which is why it cannot say what a single threshold will do on the ward.

The section "Calibration: checking an uncertainty" in [L14](../lectures/l14/notes.md) defines a calibrated output as one whose stated probabilities match what happens. The ESM's calibration plots failed that check at every horizon tested. L14's "Recalibration, and where it stops working" explains why a correction learned on one population need not carry to another. A score calibrated on the developer's encounters is calibrated on those encounters. A hospital that wants a probability, rather than a ranking, has to check calibration on its own patients.

:::{admonition} What a practitioner should take from this
:class: note
- Before deploying a vendor model, validate it on your own data, and treat the vendor's reported AUC as a claim about the vendor's data.
- Evaluate at the unit where decisions happen. For an alert that is the patient or the stay, not the individual 15-minute prediction.
- Exclude predictions made after the outcome is already recorded or acted on, and report how much your metric changes when you do.
- Compare against current practice. Count the cases the model catches that people had not already caught.
- Report precision, recall, and alert volume at the threshold you will actually use, alongside the base rate. Translate false alarms into a workload figure such as the number needed to evaluate.
- Check calibration on your own population before anyone reads the score as a probability.
:::

## Sources

- Wong A, Otles E, Donnelly JP, et al. (2021). [External validation of a widely implemented proprietary sepsis prediction model in hospitalized patients](https://pmc.ncbi.nlm.nih.gov/articles/PMC8218233/). *JAMA Internal Medicine* 181(8):1065-1070, [doi:10.1001/jamainternmed.2021.2626](https://doi.org/10.1001/jamainternmed.2021.2626). The primary source for every number on this page; the PubMed Central link is a free-to-read copy, while the publisher's page requires a subscription.
- [PubMed record 34152373](https://pubmed.ncbi.nlm.nih.gov/34152373/). The structured abstract, which states the design, outcome definition, and main results in one place, and links the journal's published correction to Table 2.
- Habib AR, Lin AL, Grant RW (2021). [The Epic Sepsis Model falls short: the importance of external validation](https://pubmed.ncbi.nlm.nih.gov/34152360/). *JAMA Internal Medicine* 181(8):1040-1041, [doi:10.1001/jamainternmed.2021.3333](https://doi.org/10.1001/jamainternmed.2021.3333). The journal's invited commentary published alongside the study.
