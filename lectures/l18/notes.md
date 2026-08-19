# L18 · Prompting, RAG, or fine-tuning: choosing the right lever

:::{admonition} At a glance
:class: tip

- **Session** L18, Week 10 · **Arc** LLM & agentic engineering
- **Slides** <a href="../../slides/l18/">Deck for this session</a>
- **Demo** [`l18-prompt-vs-rag.ipynb`](l18-prompt-vs-rag.ipynb), one corpus, one gold set, two systems scored the same way
- **Assignment** A9 is under way, released last session and due about a week out
:::

## Why this matters

The last two sessions gave you two ways to make a general model useful on your problem. L16 was prompting: instruct the model well and constrain its output. L17 was retrieval: put the right documents in front of it. This session adds the third and, more importantly, tells you how to choose among all three, because the wrong choice is expensive and common.

Here is the mistake, and it is made constantly. A team wants an assistant that knows their equipment: the specs, the standards, the internal manuals. Someone proposes to fine-tune a model "on our documents" so it learns them. They collect the PDFs, run a fine-tune, and the result is disappointing in a specific way. The model sounds more like their domain, but it still gets the actual numbers wrong, invents part numbers that look right, and cannot tell you which document any answer came from. Weeks of GPU time bought a model that is confidently wrong about the very facts it was supposed to learn. The tool was wrong for the job. Facts that must be correct, current, and cited belong in retrieval, and fine-tuning is for something else entirely.

Getting this choice right is the practitioner skill the whole adaptation unit builds toward. There are three levers, and they map onto three different kinds of need. If the gap is **knowledge** the model lacks, reach for retrieval. If the gap is **behavior**, a consistent format, style, or way of responding, that is where fine-tuning earns its place. If you are still exploring what you need, prompting is the cheapest way to find out. This session lays out that decision framework, explains fine-tuning and LoRA at the level a practitioner needs to decide for or against them, and ends with a measured bake-off between prompting and retrieval so the framework is grounded in numbers rather than assertion.

A note on what this session is not. The original plan included a hands-on LoRA fine-tune on a GPU. That has moved to an optional lab, for two reasons. A GPU training run does not reproduce for every student, and more to the point, fine-tuning is the lever an AI-in-engineering practitioner reaches for least. The durable skill is knowing when you would fine-tune and, far more often, why you would not.

## Learning objectives

By the end of this session you should be able to:

- Give a defensible answer to "should I prompt, retrieve, or fine-tune?" for a concrete engineering task.
- Explain what fine-tuning and LoRA/PEFT do, when fine-tuning is the right tool, and why engineering knowledge usually belongs in RAG instead.
- Compare prompting, RAG, and fine-tuning on cost, latency, freshness, and failure modes on the same task and metric.

## Three levers, and when each wins

```{index} model adaptation, retrieval-augmented generation, fine-tuning, prompting
```

Start with the decision, because it organizes everything else. The question is never "which technique is best" in the abstract, it is "which kind of gap am I closing," and there are three.

The first gap is **knowledge**: the model does not know a fact it needs, because the fact is proprietary, niche, or newer than its training data. Your equipment specs, your internal standards, last week's incident reports. The second gap is **behavior and format**: the model knows enough but does not respond the way you need, in the right structure, the right style, the right domain conventions, reliably every time. The third is **freshness**: the answer depends on data that changes, so whatever you do has to stay current without a rebuild.

Each lever fits one of these. **Prompting**, including few-shot examples, is the cheapest and fastest to iterate, and it is limited by the context window and by what the base model already latently knows. **Retrieval-augmented generation** is the right tool when the gap is knowledge that is large, changing, or proprietary and that must be cited, at the cost of building and maintaining retrieval infrastructure and adding latency to each call. **Fine-tuning** is the right tool when the gap is behavior or format, when you need the model to produce a specific structure or style consistently across thousands of calls, and it is poor at fast-changing facts and needs labeled data plus a real evaluation. Microsoft's own adaptation guidance frames the split the same way: choose fine-tuning for stable, specialized behavior and style, and retrieval for dynamic content and broad, current knowledge.

The levers are not exclusive, and the strongest systems combine them. A common pattern is RAG for the knowledge plus a light fine-tune for the format, so the model reliably emits your schema while retrieval keeps the facts correct and current. Hold that combination in mind while reading the rest of this session, because the decision is rarely "one of three" and often "which primary lever, and what do I add."

## What fine-tuning and LoRA actually do

```{index} full fine-tuning, LoRA, parameter-efficient fine-tuning, low-rank adapter
```
```{index} see: PEFT; parameter-efficient fine-tuning
```

To decide for or against fine-tuning you need a working picture of what it is, so here is the one-pass version. **Full fine-tuning** continues training the model on your examples and updates every weight. For a modern model that is billions of parameters in motion, which means a large GPU, a full-size copy of the weights for the optimizer state, and a checkpoint as big as the model itself. It works, and it is mostly impractical outside a well-resourced lab.

**Parameter-efficient fine-tuning** (PEFT) is the set of methods that make this feasible by training far fewer parameters, and **LoRA**, low-rank adaptation, is the one to know. The idea is to leave the base model's weights frozen and train a small add-on beside each adapted weight matrix. Where a layer computes $Wx$, LoRA adds a low-rank detour and computes $Wx + BAx$, where $B$ and $A$ are two thin matrices whose inner dimension, the **rank** $r$, is tiny, often 8 or 16. Only $B$ and $A$ are trained; $W$ never moves.

```{figure} figures/lora-adapter.png
:alt: A diagram. The input x feeds two paths: up into a blue box "W (frozen), d x d" and down into two green boxes "A, r x d" then "B, d x r". Both paths converge into an output box "h = Wx + BAx". A caption notes only A and B are trained and rank r is tiny.
:width: 100%

LoRA freezes the large weight matrix $W$ and trains a small low-rank detour $BA$ beside it. Because the rank $r$ is tiny, the adapter adds very few trainable parameters, and at inference $BA$ can be folded into $W$ so there is no extra latency.
:::

The payoff is dramatic, and it is worth seeing as a number. For a mid-size model with LoRA applied to the attention projections, the trainable parameters come to well under one percent of the model.

```{figure} figures/trainable-params.png
:alt: A bar chart on a log scale. "Full fine-tuning" is a 7.0B bar; "LoRA (r=8, q and v)" is a 4.2M bar. Text notes LoRA trains 0.06% of the weights, 1669 times fewer than full fine-tuning.
:width: 100%

Trainable parameters for a 7B model, computed for LoRA of rank 8 on the query and value projections. LoRA trains about 0.06% of the weights. Hu and colleagues, who introduced LoRA, report reducing trainable parameters by 10,000 times and GPU memory by 3 times relative to fully fine-tuning GPT-3 175B, with quality on par or better and no added inference latency.
:::

Two extensions round out the picture. **QLoRA** quantizes the frozen base model to 4-bit precision so it takes a quarter of the memory, then trains LoRA adapters on top; Dettmers and colleagues used it to fine-tune a 65-billion-parameter model on a single 48GB GPU while preserving full 16-bit task performance, and their Guanaco model reached 99.3% of ChatGPT's score on one benchmark after 24 hours of training on that single GPU. The knobs you will actually turn are the rank $r$, a scaling factor `alpha`, which weight matrices to adapt, the learning rate, and the number of epochs, and the failure you will actually hit on a small engineering dataset is **overfitting**: with a few hundred examples it is easy to train a model that memorizes them and generalizes worse than the base. None of this, notice, changes what fine-tuning is *for*. It makes fine-tuning cheap; it does not make it the right tool for knowledge.

## Why fine-tuning is the wrong lever for knowledge

```{index} knowledge injection, catastrophic forgetting
```
```{index} pair: failure mode; fine-tuning as a knowledge store
```

Return to the opening mistake, because it is the single most important thing to take from this session. Fine-tuning to inject facts fails for reasons that are structural, not fixable with more data or a bigger rank. Facts baked into weights cannot be cited, so a fine-tuned model gives you an answer with no source, which is unacceptable for a code-compliance or safety question. They go stale the moment the underlying data changes, and updating them means another training run rather than an index write. And teaching new facts by fine-tuning risks **catastrophic forgetting**, where training on the new distribution degrades what the model already knew.

This is not folklore, it has been measured. Ovadia and colleagues, in a study whose title is exactly the question of this session, compared fine-tuning against retrieval for injecting knowledge into several open models, testing both on standard benchmarks and on a purpose-built set of questions about events after the models' training cutoff. Their finding is blunt: retrieval consistently outperformed fine-tuning, for knowledge the models had seen and for entirely new knowledge alike, and the models "struggle to learn new factual information through unsupervised fine-tuning." On the genuinely new material the gap was not subtle. Retrieval answered most of the questions correctly while fine-tuning barely moved the base model's score.

### What fine-tuning is actually good at

The flip side is where fine-tuning genuinely wins: **behavior and format**. If you need a model to always emit your exact JSON schema, to adopt a house style, to follow a domain convention that no amount of prompting makes stick, or to perform a narrow classification consistently, fine-tuning bakes that behavior in so you stop paying for it in every prompt and stop having it drift. The provider fine-tuning guides say the same in their use-case lists: classification, generation in a specific format, correcting instruction-following failures, a reliable style. The rule that survives all of this is short. Knowledge is retrieval's job; behavior and format are fine-tuning's. When you find yourself about to fine-tune a model on a pile of documents so it "knows" them, stop, because what you want is an index rather than a training run.

## Evaluating adaptation apples-to-apples

```{index} pair: failure mode; unfair adaptation comparison
```

Whichever levers you compare, the comparison is only worth something if it is fair, and the standard failure is comparing a tuned model to a prompt on different data, or judging each by a different yardstick. The discipline is the one from the ML weeks: fix a single held-out set and a single metric, and run every candidate through the same gate. A fine-tune that scores 90% on its own validation data tells you nothing against a prompt scored on a different set of questions.

The demo does this honestly on a small scale, pitting prompting against retrieval on one engineering corpus and one gold set.

```{figure} figures/bakeoff.png
:alt: A grouped bar chart. For "knowledge lookup", prompting is 0% and RAG about 80%. For "absent (must decline)", prompting 0% and RAG 100%. For "formatting", both 100%. A note says RAG misses one lookup to a distractor.
:width: 100%

Prompting versus RAG on the same gold set, scored the same way. On knowledge lookups the bare prompt guesses every one wrong while retrieval grounds its answers in a cited chunk. On the query whose answer is deliberately absent from the corpus, retrieval declines while the prompt invents a confident value. On the formatting task the two tie, because there is nothing to retrieve. Computed in the demo and in `figures/make_figures.py`.
:::

Two details in that figure repay attention. Retrieval scores four of five on the knowledge lookups, one short of a clean sweep: the bolt-torque query pulled in a distractor sentence about torque in general instead of the one with the actual value, so the grounded answer was on topic and wrong. That is L17's lesson resurfacing, retrieval quality is not free, and it is exactly the kind of honest result a real evaluation surfaces and a confident assertion would have hidden. And on the formatting task retrieval and prompting tie, which is the framework in miniature: retrieval added nothing because the gap there was never knowledge.

## Cost, latency, and ops

The three levers also differ in what they cost to run and to keep running, and this often decides the matter once correctness is settled. Prompting adds nothing beyond the API call, though a long few-shot prompt is tokens you pay for on every request. Retrieval adds an index to build, store, and refresh, and a retrieval step of latency before every generation, in exchange for cited, current answers. Fine-tuning front-loads a training cost and then either a per-token premium if the provider hosts your tuned model, or the full operational burden of serving the model yourself: a GPU that stays up, a model to monitor, a checkpoint to version.

That self-hosting burden is why the case for fine-tuning a small local model over calling a large hosted one is narrower than it first looks. It can win when call volume is high enough that per-call API pricing dominates, when latency or data-residency rules forbid a hosted call, or when the task is narrow enough that a small tuned model matches a large general one. Outside those conditions, the hosted call is usually cheaper all-in once you count the engineer-hours of keeping a GPU service healthy. Count the total cost of ownership, not just the price per token.

## Where this pushes back

The framework is a guide with real edges. The levers combine, and the combination can beat either alone: RAFT, a 2024 method, fine-tunes a model specifically to be a better consumer of retrieved context, teaching it to cite the relevant passage and ignore distractor documents, and beats both plain retrieval and plain domain fine-tuning on several benchmarks. So "knowledge means RAG" does not forbid fine-tuning in a RAG system, it means do not fine-tune *instead of* retrieving for knowledge.

Retrieval has its own failure modes, and the demo showed one: a distractor outranking the answer, which no amount of grounding instruction fixes if the right chunk never gets retrieved. Fine-tuning's headline risk is using it as a knowledge store, but even for behavior it can overfit a small dataset or forget general ability. And the evaluation itself is where comparisons quietly go wrong, through a held-out set that leaks into training or a metric that flatters one lever. The honest posture is to treat every adaptation claim, including your own, as something to measure on a fair, fixed gold set before believing it.

## In-class demo

The notebook [`l18-prompt-vs-rag.ipynb`](l18-prompt-vs-rag.ipynb) runs the bake-off above end to end and offline: a small corpus of engineering-reference snippets, a gold set of the questions an engineer actually asks, a prompting baseline that answers from latent knowledge alone, and a retrieval system that does real TF-IDF retrieval and a grounded read with a confidence threshold so it can decline. It scores both on the same metric and prints the per-category table. The two moments to watch are the absent query, where retrieval declines while the prompt confidently invents a flash point, and the one knowledge query retrieval gets wrong, where a distractor sentence outranks the answer. Fine-tuning is discussed as the third lever and deliberately not trained here; the optional GPU lab is where you would run one.

## Summary

The lever follows the need. Knowledge the model lacks is retrieval's job, because retrieval keeps facts correct, current, and cited; behavior and format are fine-tuning's, because fine-tuning bakes a consistent way of responding into the weights; and prompting is the cheap first move that often tells you which of the other two you actually need. LoRA and QLoRA matter because they make fine-tuning feasible on modest hardware, training under a percent of the weights, but feasibility does not change what fine-tuning is for, and the measured evidence is clear that injecting knowledge is not it. The strongest systems combine the levers, and the only way to know a choice was right is to measure the candidates on one fair gold set. The next arc turns these adapted models into agents that call tools and take multi-step actions, where the same discipline of measuring before believing will matter more, not less.

## Resources

- [Ovadia et al., "Fine-Tuning or Retrieval? Comparing Knowledge Injection in LLMs" (2023)](https://arxiv.org/abs/2312.05934). The measured case that retrieval beats fine-tuning for knowledge; the evidence behind this session's central rule.
- [Hu et al., "LoRA: Low-Rank Adaptation of Large Language Models" (2021)](https://arxiv.org/abs/2106.09685). The method itself, with the 10,000-times parameter reduction and no-inference-latency result.
- [Dettmers et al., "QLoRA: Efficient Finetuning of Quantized LLMs" (2023)](https://arxiv.org/abs/2305.14314). Fine-tuning a 65B model on one 48GB GPU via 4-bit quantization; the Guanaco result.
- [Zhang et al., "RAFT: Adapting Language Model to Domain Specific RAG" (2024)](https://arxiv.org/abs/2403.10131). How the two levers combine: fine-tuning a model to use retrieval well and ignore distractors.
- [Augment LLMs with RAG or Fine-Tuning (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/developer/ai/augment-llm-rag-fine-tuning). A practitioner decision guide mapping fine-tuning to stable/specialized behavior and RAG to dynamic, current knowledge.
- [Hugging Face PEFT documentation](https://huggingface.co/docs/peft). The library for LoRA and friends, for the optional GPU lab rather than the core session.

## Assignment

Assignment A9, a RAG system over an engineering corpus, was released last session and is due about a week later. It asks you to build a retrieval-augmented QA system and measure both retrieval quality and answer quality against a gold set, which is the retrieval half of this session's bake-off built for real and at scale. The full specification is in [`course/assignments/a09.md`](../../course/assignments/a09.md); this page does not restate the rubric.
