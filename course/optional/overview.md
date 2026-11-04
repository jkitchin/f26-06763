# Optional material

Nothing in this section is examinable, and no assignment depends on it. It exists for a
different reason.

The syllabus is a list of tools, and tools age. The parts of this course most likely to
still be useful to you in five years are not the tools but the habits around them: how you
decide which tool deserves your attention, how you get your bearings in an area you have
never worked in, how you tell a measured result from a plausible one, and how you keep a
project honest as it grows past what one person can hold in their head. Those habits are
hard to put in a lecture, because they are not topics. They show up as the way work gets
done.

So this section collects material that shows the work rather than teaching a topic. Read it
when you are curious about the method, or when a lecture leaves you wondering how anyone
would have known that.

## What is here

Two of the documents here are halves of one argument, and the second is the one that matters. The third stands on its own.

**[How this course was built, and what to take from that](how-this-course-was-built.md)**
is a case study in tool triage and in navigating an unfamiliar problem, using this
repository's own construction as the example. It covers the conventions file that governs
every lecture and how its rules were each paid for once, the tools chosen and the reasons
including one case where the newer version lost, a table of eight claims that changed when
somebody actually measured them, what the collaboration with an AI assistant did and did not
do, and a roadmap for building the same discipline into your own work. It closes with a
reading path through the repository.

**[Generating is not learning](generating-is-not-learning.md)** is the other half, and it
argues that the first document describes an achievement that transfers to you not at all
unless you do something with the material. Producing plausible technical work has become
nearly free; consuming it costs exactly what it always did, and only the consuming half
teaches anybody anything. It covers why reading feels like enough and measurably is not,
the ten-minute diagnostic that tells you where your understanding actually stops, why
teaching works and intending to teach does not, and where the handles for all of that
already are in this repository. It ends in exercises, which is the point.

Read them in that order if you are reading both. Read only the second if you are reading
one.


**[MLOps: CI/CD for ML, drift and regression monitoring, cost, and responsible AI](mlops.md)**
is a full chapter that no session teaches. It was written as a lecture, and when the back
half of the schedule lost a slot it became optional rather than being cut down to fit
somewhere it did not belong. It covers eval gates that fail a build, measuring drift before
a label arrives to confirm it, cost as a tracked quantity rather than a surprise, a
failure-mode-to-guardrail table, and what responsible AI means for a model that steers an
engineering decision. Its demo, [`mlops-demo.ipynb`](mlops-demo.ipynb), builds an eval gate
that fails CI on purpose. The final project is where it earns its keep.

## What may be added

The section is meant to grow when there is something worth adding, not on a schedule.
Candidates, none of which exist yet:

An **annotated reading list** beyond the per-lecture resources, for people who want to go
deeper into one arc rather than broader across all of them. There is an
[open issue](https://github.com/jkitchin/f26-06763/issues/35) collecting suggestions.

A **postmortem of the assignments**, written after they have been graded once, recording
which parts turned out to teach what they were supposed to and which did not.

A **guide to the engineering datasets** used across the semester: where each comes from,
what is wrong with it, and what it can and cannot support. Several are already discussed in
the lectures that use them, but the survey view would be useful when you are choosing data
for a capstone.

If you work through something in this course and find that the useful part was a method
nobody wrote down, that is a good candidate for this section. Say so.
