# Generating is not learning

:::{admonition} At a glance
:class: tip

- **Optional**, and the second half of
  [How this course was built](how-this-course-was-built.md). That document is about
  producing the material. This one is about the fact that producing it taught the producer
  a great deal and transfers none of that to you.
- **The claim.** Generating plausible material is now nearly free. Consuming it costs
  exactly what it always did. Only the consuming half teaches anyone anything.
- **What to do with it.** It ends with exercises against this repository. The document is
  self-defeating if you only read it.
:::

## The half the other document left out

The companion document describes how this course's material was produced, and it is
honest about the process. It is also, read on its own, subtly misleading, because it can
leave the impression that the achievement was the production.

It was not. Fourteen sets of lecture notes exist, and every hour of understanding that went
into making them stayed with the people and processes that made them. The notes themselves
are inert. They are a record of somebody else's thinking, and a record of thinking is not
thinking, in exactly the way that a photograph of a squat is not exercise.

This matters more now than it used to, and the reason is an asymmetry that changed
recently and changed only on one side.

## What got cheap, and what did not

Producing plausible technical material used to be slow. That was an accident of the
technology, but it had a useful side effect: the cost of production forced consumption.
You could not write a chapter without understanding the chapter. The effort was not
separable from the learning, so nobody had to be told to do the learning part.

That coupling is gone. The material in this repository was produced in seventeen days.
Reading it once, carefully and without doing anything, is about nine hours of work, and
working through it properly, running the notebooks and re-deriving the numbers, is several
times that. **Production accelerated by an order of magnitude. Consumption did not
accelerate at all**, because it is bounded by how fast a human being can be changed by
something, and nothing has made that faster.

So the ratio inverted, and a new failure mode arrived with it. It is now entirely possible
to accumulate a large, well-organized, genuinely correct body of material that nobody has
metabolized. Everyone involved will feel productive. The repository will look like
progress. And the understanding it was supposed to produce will not exist anywhere.

The blunt version, which is worth saying because the polite version does not land:
**generated material you never consume is worse than material you never generated.** Not
neutral, worse. It occupies the slot where understanding would have gone, it feels like an
asset, and it postpones the discovery that you cannot actually do the thing until the
moment you have to do the thing.

## Reading feels like enough. It is measurably not.

This is not a moral point about diligence. It is a measured effect, and the measurement is
unusually clean.

Roediger and Karpicke ran the study in 2006. Students read prose passages, then either
restudied them or took recall tests on them. Retention was measured at five minutes, two
days, and one week. **Restudying won at five minutes and lost at two days and at one
week.** Testing, which feels worse and produces more errors while you are doing it,
produced substantially better retention later.

The part to sit with is what happened to the students' own judgment. Repeated studying
**raised their confidence** in their ability to recall the material, while lowering their
actual recall relative to the tested group. The subjective signal moved in the opposite
direction from the objective one. They were not lazy. They were misinformed by their own
sense of fluency.

Now apply that to the tool you have. Asking a model to explain something and reading a
clear, well-organized answer is restudying, with the fluency turned up. The explanation is
more coherent than the one you would have written, which makes it *feel* more like
understanding than your own halting version would have. That feeling is the thing the
experiment tells you not to trust.

This is the course's own lesson pointed back at you. The lectures repeat that plausible
output is the failure mode to fear, that a number which looks fine is the one that gets
shipped. The same is true of your sense that you have understood something. Fluent input
produces a confident reader, and confidence is not the variable you were trying to move.

## The cheapest diagnostic anyone has found

If confidence is unreliable, you need a test. There is a good one and it takes ten minutes.

Rozenblit and Keil, in 2002, asked people to rate how well they understood how ordinary
things work: a zipper, a flush toilet, a helicopter. Then they asked them to write out the
mechanism, in detail, step by step. Then they asked them to rate their understanding again.

**The ratings fell.** Not because anyone had taken knowledge away, but because attempting
the explanation is what reveals whether the explanation exists. The authors called the gap
the *illusion of explanatory depth*, and they showed it is far stronger for explanatory
knowledge, how something works, than for facts or procedures. Which is precisely the kind
of knowledge this course is made of.

The practical consequence is a habit you can start today and that costs almost nothing:

> Close the notes. Write the mechanism from memory, in full sentences, as if to somebody
> who has not read them. Stop when you stall, and note where.

Where you stall is not a gap in the notes. It is the actual current state of your
knowledge, which up to that moment you had no way to see. Then go back and read only the
part you stalled on. That is a targeted, ten-minute intervention aimed at a real deficit,
which is worth more than an hour of rereading aimed at a feeling.

## Teaching is the strongest form, and intending to teach is not

The folk wisdom that you do not understand something until you teach it turns out to be
about half right, and the half that is wrong is the half people rely on.

Fiorella and Mayer separated two things that usually travel together: *expecting* to teach,
and *actually* teaching. College students learned the Doppler effect. Some expected a test;
some expected to teach. Of those expecting to teach, some then actually taught, by
recording a video lecture for a fictitious student.

On immediate comprehension tests, the students who merely prepared to teach did about as
well as those who actually taught. **On the delayed test, the ones who actually taught
performed best**, and preparation alone was not enough to produce the lasting effect.

So "I'll explain this to someone at some point" does not count, and neither does reading
with the intention of one day teaching it. The benefit lives in the act. You have to
produce the explanation out loud, in real time, to somebody who can look confused. The
looking confused is load-bearing: it is a signal you cannot generate for yourself and
cannot get from a model, which will accept a muddled explanation without flinching.

There is a reason the slide decks in this repository carry speaker notes and timing cues in
HTML comments. A deck is not a document. It is an instrument for the person delivering it,
and delivering it is where the gaps in the delivery surface, reliably, in front of
witnesses. That is uncomfortable and it is the mechanism.

## This repository was built to be consumed

Most of the affordances are already here, and they are easy to miss if you treat the notes
as the deliverable. An inventory of the handles, and what each is for:

| what it is | what it is for | what happens if you skip it |
|---|---|---|
| **demo notebooks that break on purpose**, three documented defects in `l01-reproducibility.ipynb` | you cannot read a failing notebook passively; you have to diagnose it | you never find out which of the three you routinely ship |
| **figure scripts that print every number**, ten of them | you can re-derive a claim instead of believing it | you inherit somebody else's arithmetic and never test yours |
| **"predict before we compute" prompts** in the demos and speaker notes | forces a commitment before the answer is visible, which is the only way to be surprised | the result looks obvious in hindsight, and hindsight teaches nothing |
| **`## Where this pushes back` sections** in the notes | gives you something to argue with rather than absorb | you leave believing the tool is better than it is |
| **the 148 code cells across the demo notebooks** | each one is a place to change something and predict what breaks | the notebook becomes a screenshot |
| **speaker notes in the decks** | the deck is a script for delivering, not a summary for reading | you use the deck as worse notes |

If you only read the notes, you are using perhaps a fifth of what is in this repository,
and specifically the fifth that the research above says works least well.

## A consumption ladder

Ordered by effort. The return rises with the rung, and so does the discomfort, which is not
a coincidence. Nothing on this ladder is optional in the sense of being decorative; the
lower rungs are simply what you do when you have ten minutes instead of an hour.

| rung | what you do | what it costs | what it proves |
|---|---|---|---|
| 0 | read it | an hour | nothing. You have been exposed to it |
| 1 | read it, writing down a prediction before each measured result | +2 minutes a claim | that you had a model, and whether it was right |
| 2 | re-derive one number without looking at the answer | 15 minutes | that the number is yours now |
| 3 | run the demo, then break it deliberately and predict the error | 30 minutes | that you know which parts are load-bearing |
| 4 | change one assumption in a figure script, predict what moves, then re-run | an hour | that you understand the mechanism, not the result |
| 5 | close everything and write the mechanism from memory | 10 minutes | where your knowledge actually stops |
| 6 | teach ten minutes of it, out loud, to one real person | 30 minutes plus their patience | almost everything. This is the one that works |
| 7 | find something wrong in the material and fix it upstream, with evidence | varies | that you have passed the material and are now maintaining it |

Rung 6 is the one to protect if you protect only one. Rung 0 is the one that will eat your
week if you let it.

## Exercises against this repository

These are specific on purpose. Each names an artifact, a prediction to commit to before you
look, and a way to check yourself. Do one properly rather than six loosely.

**E1. The gradient that should have agreed.** Before running anything, write down whether
you expect PyTorch and JAX to agree with an analytically computed gradient, and to how many
digits. Then run `lectures/l11/figures/make_figures.py` and look at the autodiff panel. One
framework agreed to about 3e-16 and the other to about 5e-8. Write three sentences
explaining the gap before you read the script's header, which explains it. If your
explanation does not mention dtype, you have found a real gap in your own model of
floating-point arithmetic, and it is a gap that will cost you a day at some point.

**E2. Three ways to break a notebook.** Run `lectures/l01/l01-reproducibility.ipynb` and
expect it to fail. It is deliberately defective in three documented ways. Fix each one.
Then answer honestly, in writing: which of the three have you personally shipped in your
own work in the last year? Most people have shipped at least two.

**E3. Predict the similarity ordering.** In `lectures/l15/l15-tokens-embeddings.ipynb`,
there are three pairs of maintenance-log entries: one pair describing the same event in
different words, one pair where the second entry negates the first, and one pair differing
only by a unit. Rank them by expected cosine similarity **before** running the cell. Most
rooms get the negation exactly backwards. If you did too, write down why the model behaves
that way, in one paragraph, without looking at the notes.

**E4. Move one assumption.** Pick any `figures/make_figures.py` in the repository. Change
exactly one constant: a sample size, a split rule, a random seed, a model choice. Predict
what moves, by how much, and in which direction, then re-run. The interesting outcome is
not when you are right. It is when a number you expected to be stable is not, which tells
you the conclusion was resting on something you had not noticed.

**E5. Teach ten minutes.** Choose one `## Where this pushes back` section from any lecture.
Teach it, out loud, to one other person, for ten minutes, without notes. Not a summary of
what the section says: the argument for why the limitation exists, and what you would do
about it. Note every question you could not answer. Those are your next reading list, and
they are a better one than any you would have written for yourself.

**E6. Fix something upstream.** Find one thing in this repository that is wrong, unclear,
out of date, or missing, and open an issue with the evidence for it. "Evidence" means the
same two-step standard the lectures use: the artifact, and what it actually says. This is
rung 7, it is the only exercise here that improves the material for the next person, and
the number of students who do it is usually zero.

## A schedule small enough to actually happen

"Consume more" is not a plan, and an ambitious plan you abandon in week three is worse than
a modest one you keep. Three commitments, chosen to be small:

**Before each session**, spend fifteen minutes on the notes at rung 1: skim for the
measured claims and write down what you expect each one to be. Not the whole set of notes.
Just the numbers.

**After each session**, spend ten minutes at rung 5: close everything and write the
mechanism of the one idea you would most want to have understood. Where you stall is your
reading assignment.

**Once per module**, do rung 6 once. Ten minutes, out loud, to one person. Trade with
someone doing the same thing and you have both covered the whole semester for the cost of
twenty minutes a fortnight.

That is roughly ninety minutes a week, and it will do more than doubling your reading time
would.

## What this document cannot do

It cannot make you do any of this, and it is aware of the irony that it is itself generated
material that you can read fluently and put down. If you have read this far and do nothing
else, the document has demonstrated its own thesis at your expense.

It is also not a claim that reading is worthless. Reading is how you find out what exists
and what the vocabulary is, and you cannot practice retrieval on material you have never
encountered. The argument is narrower: **reading is the beginning of consumption and is
routinely mistaken for the whole of it**, and the mistake got much easier to make when
generating readable material became free.

Finally, the exercises are real work and this course already has assignments that are also
real work. Take the one rung you will actually do. A single honest ten-minute explanation to
one person beats a ladder you admire and never climb.

## Resources

- [Roediger and Karpicke, *Test-enhanced learning: taking memory tests improves long-term
  retention*](https://pubmed.ncbi.nlm.nih.gov/16507066/) (2006), *Psychological Science*.
  The experiment described above. The finding that matters is not that testing works; it is
  that restudying raised confidence while lowering retention, so your own sense of how well
  you know something is the wrong instrument.
- [Rozenblit and Keil, *The misunderstood limits of folk science: an illusion of
  explanatory depth*](https://cogdevlab.yale.edu/sites/default/files/files/rozenblit%20&%20keil%20%202002.pdf)
  (2002), *Cognitive Science* 26, 521-562. Openly readable copy from the authors' lab.
  Long, and you only need Study 1 to get the tool: rate, explain, re-rate.
- [Fiorella, *Learning by Teaching*](https://www.unh.edu/teaching-learning-resource-hub/sites/default/files/media/2023-06/itow-learning-by-teaching-fiorella.pdf),
  a thirteen-page chapter summarizing the evidence, including the Fiorella and Mayer (2013,
  2014) experiments separating expecting to teach from actually teaching. Read this one
  before you decide the ladder's top rung is optional.
- [*Make It Stick: The Science of Successful Learning*](https://www.hup.harvard.edu/books/9780674729018),
  Brown, Roediger and McDaniel (2014). Book-length treatment of the same body of work,
  including desirable difficulties and spacing. Worth it if you want the general case
  rather than the three studies above.
- The **Feynman technique**, which is the folklore version of rungs 5 and 6 and is usually
  presented without evidence. Labelled as folklore here on purpose. It happens to describe
  the right procedure, and the papers above are why it works, which is a better reason to
  do it than that somebody attributed it to a famous physicist.
