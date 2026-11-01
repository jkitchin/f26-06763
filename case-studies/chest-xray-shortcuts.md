# Case study · Chest X-ray models that learned the hospital

:::{admonition} At a glance
:class: tip
- **Field**: Biomedical engineering, medical imaging
- **Connects to**: [L12 · Architectures for engineering data](../lectures/l12/notes.md), [L1 · The AI-engineering landscape](../lectures/l01/notes.md), [L10 · Classification](../lectures/l10/notes.md)
- **Primary source**: Zech et al. (2018), *PLOS Medicine*; with DeGrave, Janizek and Lee (2021), *Nature Machine Intelligence*
:::

## Why this matters

A convolutional network trained to find pneumonia on chest radiographs can score well on held-out images and still be reading the wrong thing. In 2018, Zech and colleagues at Mount Sinai showed that such a network could tell which hospital an X-ray came from almost perfectly. Because the hospitals had very different rates of pneumonia, knowing the hospital was already most of the way to a good score.

The study followed standard practice. It reproduced a published architecture, split its data by patient, stopped training early on a tuning set, and reported every number on test images it had never seen. The internal test scores were real. They described a model that partly detected disease and partly detected the scanner, the department, and the hospital's patient mix. Only testing at a hospital that contributed no training data separated the two.

This is the same failure Lecture 1 described for Google Flu Trends, moved from search queries to pixels. It matters to anyone who trains an image model on data pooled from several sources: several labs, several test rigs, several cameras, or several plants.

## The setting

Zech et al. assembled 158,323 frontal chest radiographs from three hospital systems. The NIH Clinical Center contributed 112,120 images from 30,805 patients, Mount Sinai Hospital (MSH) contributed 42,396 from 12,904 patients, and the Indiana University Network for Patient Care (IU) contributed 3,807 from 3,683 patients. The NIH and IU sets were public; the Mount Sinai set was the authors' own.

The labels came from the written radiology reports. NIH labels were extracted from radiology reports by a natural language processing (NLP) system. IU labels were assigned by curators who read the reports. For Mount Sinai, the authors hand-labeled 405 reports and trained their own NLP model to label the rest.

The model was a DenseNet-121, pretrained on ImageNet photographs and fine-tuned on the radiographs, with every image resized to 224 by 224 pixels. That choice followed CheXNet, an earlier high-profile pneumonia model, so the results would be comparable. NIH and MSH patients were split 70/10/20 into train, tune, and test groups by patient, so no person's images appeared on both sides. All of IU was held back as an external test set for the pneumonia task.

Performance was reported as AUC, the area under the receiver operating characteristic curve. AUC measures how well the model's scores rank positive cases above negative ones across every possible threshold. A value of 0.5 is a coin flip and 1.0 is a perfect ranking.

## What happened

The first result was that the three hospitals had very different amounts of pneumonia. In the labeled data, 34.2% of Mount Sinai radiographs were positive, against 1.2% at NIH and 1.0% at IU. The gap was large enough that the authors built a trivial model that ignored the image entirely and scored each X-ray by its hospital's training prevalence. On the combined MSH and NIH test set, that model reached an AUC of 0.861.

The CNNs then did better at home than away in three of the five natural comparisons. A model trained on NIH data scored 0.750 on NIH test images and 0.695 on Mount Sinai images. A model trained on Mount Sinai data scored 0.802 internally and 0.717 at NIH. Both of those drops were statistically significant. Against the small IU set, neither single-site model was significantly worse than at home, though the IU confidence intervals were wide.

The pooled model gave the clearest result. Trained on MSH and NIH together, it reached an AUC of 0.931 on the joint test set, the highest internal score in the study. On IU, a hospital it had never seen, it fell to 0.815. It also scored only 0.805 on the Mount Sinai test images alone and 0.733 on the NIH ones alone. The joint score was higher than either piece because part of what it ranked was which hospital each image came from.

The authors then trained a CNN to predict the hospital system directly. It identified 22,050 of 22,062 NIH test images (99.95%), 8,386 of 8,388 Mount Sinai images (99.98%), and 737 of 771 IU images (95.59%). Within Mount Sinai, a second CNN separated portable radiographs from inpatient wards and from the emergency department with 100% accuracy on 5,805 and 449 test images. The two groups had different pneumonia rates, 41.1% on the wards against 32.8% in the emergency department.

Finally, they ran a controlled experiment. They subsampled cohorts of 10,000 MSH and 10,000 NIH patients with the same overall pneumonia rate but different splits between hospitals. When both hospitals had the same 5% prevalence, internal and external AUC agreed (0.739 against 0.732 at IU). When nearly all the pneumonia was placed at Mount Sinai, internal AUC rose to 0.899 and IU AUC fell to 0.641. Making the hospital more predictive of the label made the internal score better and the external score worse.

## Why it happened

The mechanism is confounding through the data source. A confounder is a variable that influences both the input and the label. Here the hospital determines what the image looks like (scanner, processing, markers, positioning) and also how likely the patient is to have pneumonia (inpatients against outpatients, and how liberally each labeling process called a study positive). A model trained to reduce its loss will use any feature that predicts the label, and the hospital's signature was easier to read than the disease.

That signature was spread across the whole image. Using activation maps on 100 NIH test images, the authors found that on average 35.7 of the 49 image subregions could each identify NIH with at least 95% confidence. The laterality markers were especially influential: the metal tokens technicians place in the corner of the field to mark the patient's left or right. Inside Mount Sinai, the authors found after the fact that the ward and emergency department used scanners from different manufacturers (Konica Minolta and Fujifilm). The emergency department images were stored with inverted gray levels and distinctive text. None of this was visible to the team until they reviewed images by hand.

A second study shows how general this is. DeGrave, Janizek and Lee (2021) looked at the COVID-19 detectors published early in the pandemic. Many were trained on positive images from one collection, often cropped from journal figures, and negative images from another, such as the NIH set. The data source then correlated perfectly with the label. Their reproduced models lost about half of their predictive performance on an external dataset. The gap appeared in all nine additional architectures they tried, and a logistic regression and a small CNN did no better. When they swapped the laterality markers between a positive and a negative image, the model's predicted odds of COVID-19 moved with the marker.

The course name for this is a **shortcut**. DeGrave et al. use the word for spurious associations between the label and features that reflect how an image was acquired. In plain terms, a shortcut is a feature that predicts the label in the training data for a reason unrelated to the thing the label describes.

## Connections to the lectures

The section on CNNs for fields and images in [L12](../lectures/l12/notes.md) explains why a convolutional network suits a grid: parameter sharing lets a feature learned in one place be detected anywhere. A corner marker or a border artifact is easy to learn for the same reason. The prior that makes a CNN efficient for a stress field also makes it efficient at finding the scanner's fingerprint. L12's section asking whether the architecture earns its keep argues for always running a strong classical baseline. Zech's hospital-prevalence model is that baseline, and it scored 0.861 without looking at a pixel. Any CNN result on the pooled data had to be read against it. L12's limitations section also calls an architecture an assumption to check. DeGrave et al. found that a logistic regression showed the same generalization gap, which places the problem in the data.

The section on validating well in [L1](../lectures/l01/notes.md) makes the general point with Google Flu Trends, which held out data carefully and was still "part flu detector, part winter detector". These pneumonia models were part pneumonia detector and part hospital detector. L1's section on why engineering data is different also applies directly: the radiograph is a measurement, and the scanner, its processing, and its calibration are part of the measurement. Zech et al. found that hospital system was a larger source of variation in the principal components of the image data than pneumonia was.

The section on data leakage in [L7](../lectures/l07/notes.md) frames leakage as information the model would not have at prediction time. A confounder is a related problem with one difference: the hospital signature is available at prediction time, but its link to the label holds only in the training population. L7's habit of naming the group key carries over. In this study the patient was the group key for the split, and the authors used it correctly. The hospital was a second grouping that a patient-level split could not control.

Finally, the section on measuring a classifier in [L10](../lectures/l10/notes.md) shows that the chosen metric depends on the test population. The same model here scored 0.931 on a pooled test set and 0.733 on one of its parts. L10's section on faults the classifier never saw carries the same warning: a model is reliable only on cases that resemble its training data.

:::{admonition} What a practitioner should take from this
:class: note
- Before training on pooled data, tabulate the label rate by source (site, rig, camera, operator, batch). A large difference means the source alone can score well, so build the source-only model and report its score as the baseline.
- Train a model to predict the source from the inputs. If it succeeds, your inputs carry a fingerprint your label model can use.
- Hold out at least one entire source that contributes nothing to training or tuning, and report internal and external scores side by side. A patient-level or sample-level split does not test this.
- Look at the images, or the raw signals, by hand, grouped by source. The authors spotted the inverted gray levels at Mount Sinai only after manual review.
- Do not treat a good external score as proof. DeGrave et al. show some shortcuts transfer between datasets, so check what the model attends to as well.
:::

## Sources

- [Zech, Badgeley, Liu, Costa, Titano and Oermann, "Variable generalization performance of a deep learning model to detect pneumonia in chest radiographs: A cross-sectional study", *PLOS Medicine* 15(11): e1002683 (2018)](https://doi.org/10.1371/journal.pmed.1002683). The primary source for every Zech number on this page; open access, with the hospital-prediction and engineered-prevalence experiments in the Results.
- [cxr-generalize code repository](https://github.com/jrzech/cxr-generalize). The authors' training and evaluation pipeline, linked from the paper's data availability statement; worth reading to see how the site-level splits were built.
- [DeGrave, Janizek and Lee, "AI for radiographic COVID-19 detection selects shortcuts over signal", *Nature Machine Intelligence* 3: 610 to 619 (2021)](https://doi.org/10.1038/s42256-021-00338-7). The second study; free to read on the publisher's site, and the clearest demonstration that swapping a laterality marker changes the prediction.
- [DeGrave, Janizek and Lee, medRxiv preprint 2020.09.13.20193565](https://doi.org/10.1101/2020.09.13.20193565). An open CC BY preprint of the same study, if the publisher page is unavailable; the published version differs in places, so cite the journal.
