# Case study · Heartbeat classification and the patient split

:::{admonition} At a glance
:class: tip
- **Field**: Biomedical engineering
- **Connects to**: [L9 · Regression and cross-validation](../lectures/l09/notes.md), [L10 · Classification](../lectures/l10/notes.md), [L12 · Architectures for engineering data](../lectures/l12/notes.md)
- **Primary source**: de Chazal, O'Dwyer and Reilly (2004), *IEEE Transactions on Biomedical Engineering* 51(7), 1196 to 1206
:::

## Why this matters

A heartbeat classifier that scores 98.7% in a paper can score 76.3% on the same database once the test set holds only patients the model has never seen. Both numbers describe the same method, re-implemented and run on the same recordings. The only thing that changed is which heartbeats were allowed into the training set.

Automatic heartbeat classification is a real clinical task. Some arrhythmias appear so rarely that a Holter monitor may have to record a patient's electrocardiogram (ECG) for up to a week to catch them, and a cardiologist cannot read every beat of that. Software labels the beats so that the rare abnormal ones can be found and counted. The software will always be used on a new patient, because nobody buys a Holter analyzer to re-read the recordings it was trained on. An evaluation that lets the model see the test patient during training answers a question no clinic asks.

The case is useful for this course because the error is the same one Lecture 9 measured on concrete mixes and Lecture 12 guarded against on turbofan engines. A patient here plays the role an engine plays there. The cardiology literature learned this from a body of published results that proved optimistic, and adopted a standard split afterwards.

## The setting

The data almost everyone uses is the [MIT-BIH Arrhythmia Database](https://physionet.org/content/mitdb/1.0.0/), distributed free on PhysioNet. It holds 48 half-hour excerpts of two-channel ambulatory ECG recordings from 47 subjects, recorded by the Beth Israel Hospital Arrhythmia Laboratory in Boston between 1975 and 1979. Twenty-three recordings (numbered 100 to 124) were chosen at random from a set of over 4000 Holter tapes. The other 25 (numbered 200 to 234) were picked from the same set to include rare but clinically important arrhythmias. The signals were digitized at 360 samples per second per channel. Two or more cardiologists annotated every beat independently and resolved their disagreements, which gives about 110,000 reference labels.

Each recording is one patient, with a single exception: records 201 and 202 came from the same man, according to the [database directory](https://archive.physionet.org/physiobank/database/html/mitdbdir/intro.htm). And a recording carries thousands of beats from one heart, measured through one set of electrodes on one tape recorder.

The classification task follows a standard from the Association for the Advancement of Medical Instrumentation (AAMI EC57). It groups the database's beat types into five classes: N (normal and bundle branch block beats), S (supraventricular ectopic beats, SVEB), V (ventricular ectopic beats, VEB), F (fusion of a normal and a ventricular beat), and Q (unknown or paced). The classes are badly imbalanced. In de Chazal's test half of the data, class N is about 89% of the beats and class S is about 3.7%. The clinically interesting beats are the rare ones.

## What happened

Philip de Chazal, Maria O'Dwyer and Richard Reilly set out in 2004 to build a heartbeat classifier from linear discriminants on hand-built features: intervals between beats (RR intervals), QRS and T-wave durations, and samples of the waveform shape. They removed the four recordings with paced beats, as the AAMI standard recommends, and split the remaining 44 recordings into two halves of 22 recordings each, with about 50,000 beats apiece and a similar mix of beat types. They called the halves DS1 and DS2. All model selection happened inside DS1 by cross-validation, and DS2 was touched once, for the final score.

The finding that made the paper a reference came from running the same cross-validation two ways on DS1. In one division (they called it DD1), each of the 22 folds held one whole recording, so the model was always scored on a patient absent from its training folds. In the other (DD2), every beat was treated as independent and assigned to one of 22 folds at random, so beats from every patient appeared on both sides. For their configuration I, the [paper's Table VI](https://web.archive.org/web/20060514090303/http://dsp.ucd.ie:80/dspfiles/main_files/pdf_files/PdeC_HeartBeatjuly04.pdf) gives these results:

| Cross-validation folds | Accuracy | SVEB sensitivity | VEB sensitivity | Fusion sensitivity |
|---|---|---|---|---|
| Random beats (DD2) | 86.1% | 77.6% | 76.4% | 87.0% |
| Whole recordings (DD1) | 79.0% | 59.9% | 65.3% | 74.5% |

The random-beat folds reported 7.1 points more accuracy and 17.7 points more SVEB sensitivity than the folds of whole recordings. The authors concluded that dividing data on a beat basis gives optimistically biased results, that this scheme had been favored by earlier investigators, and that it should be avoided. Their final classifier, trained on DS1 and scored once on DS2, reached a sensitivity of 75.9% and a positive predictivity of 38.5% for SVEB, and 77.7% and 81.9% for VEB.

Twelve years later, a survey by [Luz, Schwartz, Cámara-Chávez and Menotti (2016)](https://doi.org/10.1016/j.cmpb.2015.12.008) named the two protocols. The **intra-patient** paradigm puts beats from the same patients in training and test. The **inter-patient** paradigm keeps patients apart, and de Chazal's DS1/DS2 split is its standard form. The survey reports that many intra-patient methods claim accuracies above 98%. It also summarizes an earlier study by Luz and Menotti that re-implemented published methods and scored each under both protocols. Two of the five rows from its Tables 9 and 10 show the scale:

| Method (as re-implemented) | Accuracy, random beats | Accuracy, DS1/DS2 | SVEB sensitivity, random beats | SVEB sensitivity, DS1/DS2 |
|---|---|---|---|---|
| Song et al. | 98.7% | 76.3% | 86.4% | 27.0% |
| Ye et al. | 96.5% | 75.2% | 72.4% | 3.2% |

The overall accuracy fell by about 21 points. The sensitivity for the rare class collapsed: Ye's method went from catching nearly three supraventricular ectopic beats in four to catching about one in thirty. The survey's recommendation was direct. Use the inter-patient DS1/DS2 split so that results can be compared fairly, and tune hyperparameters by cross-validation over patients inside DS1.

## Why it happened

Beats from one recording are not independent samples. A person's heart has its own shape of QRS complex, its own resting rate, and its own ectopic focus if it has one. Each recording also has its own lead configuration and was made on one of nine tape recorders, whose mechanical artifacts the database directory documents. A given patient's beats therefore share a waveform shape, an amplitude scale, and a noise signature. de Chazal and colleagues put it in one clause: intrasubject beats can be highly dependent.

When beats are shuffled into folds at random, almost every test beat has near-copies in training from the same patient, often seconds apart. A flexible model can score well by recognizing the patient and recalling what that patient's abnormal beats looked like, which is memorization of individuals. It need not learn what makes a beat ventricular. The rare classes suffer most under the honest split because each rare beat type comes from only a few recordings. In de Chazal's Table II, for example, all 16 atrial escape beats in the data come from a single recording. Once a patient like that is held out, the model has no example of the beat type left to learn from.

The standard split itself has one gap. de Chazal's Table II lists record 201 in DS1 and record 202 in DS2, and PhysioNet states that both came from the same subject. The survey by Luz and colleagues notes this too. The inter-patient protocol is therefore inter-recording, which is almost but not exactly inter-patient. The unit of independence has to be checked against the metadata, not assumed from the file names.

## Connections to the lectures

The section on grouped rows and `GroupKFold` in [Lecture 9](../lectures/l09/notes.md) is this case with a different unit. There, 1,030 concrete rows collapsed into 428 distinct mixes, and random folds put the 28-day test of a mix in training and the 56-day test of the same mix in validation. The flexible models lost the most when the folds were made of whole mixes, the decision tree by 36%, while the linear models barely moved. de Chazal's DD1 is `GroupKFold` with one group per recording, and their DD2 is shuffled `KFold`. Lecture 9's practitioner box lists a patient among the units to ask about.

The section on measuring a classifier in [Lecture 10](../lectures/l10/notes.md) explains why accuracy hid most of the damage. There, a detector that always answers normal scores 85.4% on the plant data and never catches a fault. With about 89% normal beats in DS2, an always-normal heartbeat classifier would do slightly better than that. Cardiology reports **sensitivity** and **positive predictivity**, which are Lecture 10's recall and precision under their clinical names, and computes them per class. Read per class, the 3.2% SVEB sensitivity in the table above is a classifier that misses almost every beat it exists to find. Lecture 10's section on faults the classifier never saw also applies. A supervised model catches new cases only when they resemble its training cases, and a new patient is a new case of exactly that kind.

The turbofan work in [Lecture 12](../lectures/l12/notes.md) uses the same discipline in a sequence setting. Its remaining-useful-life comparison scores every model with `GroupKFold` by engine, so that no engine's windows appear in both training and validation, and it windows the sensor data so that no window straddles two engines. An engine in C-MAPSS is a patient in MIT-BIH. Each one produces many correlated rows, carries its own baseline and degradation path, and is the thing the deployed model will face as a stranger. Splitting by window would let a network recognize the engine, as splitting by beat lets a classifier recognize the patient.

:::{admonition} What a practitioner should take from this
:class: note
- Before choosing a splitter, name the unit you will deploy on: a patient, an engine, a mix, a batch. Put each unit wholly in training or wholly in test, and use `GroupKFold` (or leave-one-group-out) for the folds inside the training set as well.
- Check the unit against the metadata. Two recordings can share one patient, and two files can share one specimen. A grouping column built from file names can leak.
- When a public benchmark has a standard grouped split, such as DS1/DS2 for MIT-BIH, use it and say so, so your number can be compared with others.
- Report per-class sensitivity and positive predictivity, not accuracy alone, whenever the class you care about is rare.
- Run both splits once as a diagnostic. A large gap between random and grouped scores measures how much your model memorizes units, and the grouped score is the one to report.
:::

## Sources

- de Chazal, P., O'Dwyer, M., Reilly, R. B. (2004). Automatic classification of heartbeats using ECG morphology and heartbeat interval features. *IEEE Transactions on Biomedical Engineering* 51(7), 1196 to 1206. https://doi.org/10.1109/TBME.2004.827359. The primary source for the DS1/DS2 split and the beat-based versus record-based comparison (Table VI and Section VI). The open link is an [archived copy from the authors' former University College Dublin site](https://web.archive.org/web/20060514090303/http://dsp.ucd.ie:80/dspfiles/main_files/pdf_files/PdeC_HeartBeatjuly04.pdf), served by the Internet Archive.
- Luz, E. J. S., Schwartz, W. R., Cámara-Chávez, G., Menotti, D. (2016). ECG-based heartbeat classification for arrhythmia detection: A survey. *Computer Methods and Programs in Biomedicine* 127, 144 to 164. https://doi.org/10.1016/j.cmpb.2015.12.008. Names the intra-patient and inter-patient paradigms and tabulates the same methods under both (Tables 9 and 10). A copy is also in the [Universidade Federal de Ouro Preto repository](http://www.repositorio.ufop.br/handle/123456789/7011).
- Moody, G. B., Mark, R. G. [MIT-BIH Arrhythmia Database](https://physionet.org/content/mitdb/1.0.0/), PhysioNet. The dataset itself, with its size, sampling rate, and annotation process, free to download.
- [MIT-BIH Arrhythmia Database Directory, introduction](https://archive.physionet.org/physiobank/database/html/mitdbdir/intro.htm), PhysioNet archive. How the records were selected and the note that records 201 and 202 come from the same subject.
- scikit-learn, [cross-validation of grouped data](https://scikit-learn.org/stable/modules/cross_validation.html). The user guide section behind `GroupKFold`, `LeaveOneGroupOut`, and related splitters used in Lecture 9.
