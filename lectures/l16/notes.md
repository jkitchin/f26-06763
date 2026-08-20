# Lecture 16: The API, prompt, and structured-output interface

:::{admonition} Overview
:class: tip

- **Session** Lecture 16, Week 9
- **Arc** LLM and agentic engineering
- **Slides** <a href="../../slides/l16/">Deck for this session</a>
- **Demo** [`l16-structured-extraction.ipynb`](l16-structured-extraction.ipynb), a datasheet turned into a validated parts record, and what happens when it cannot be
- **Assignment 8** released last session, due about a week out
:::

## Why this matters

The previous session treated a large language model as an object of study: tokens in, a next-token distribution out. This session treats it as a component in a system you are responsible for. You call it over an API, you pay for every token in both directions, it answers on its own schedule, and the thing it hands back is text that you now have to trust enough to write into a database. Every one of those is an engineering constraint, and none of them is visible from a chat window.

Here is the task that makes them concrete, and it is the task behind Assignment 8. You have a few hundred component datasheets, one per valve or pump or fastener, each a page of units-heavy prose and half-tables, no two laid out the same way. You want a clean parts table: part number, material, maximum pressure in megapascals, operating temperature range, mass. A language model can read a datasheet and produce that record, which is exactly the kind of messy-text-to-structured-data job that used to need a human. The trouble is what "produce that record" hides.

Consider the ways it goes wrong, none of which raise an exception. The model returns valid JSON with `max_pressure_MPa: 42`, and the datasheet said 42 bar, which is 4.2 MPa, so your table is off by a factor of ten and nothing complained. The model is handed a datasheet that genuinely omits the pressure rating and, rather than leave the field empty, it invents a plausible 16 MPa because inventing plausible text is what it was trained to do. Someone pastes a sixty-page manual into a single call, the input runs past the context window, the provider silently drops the end, and the answer is extracted from a truncated document. In each case you got JSON back, the program ran, and the number is wrong. **"The model returned JSON" is not the same claim as "the JSON is correct,"** and the entire discipline of this session is the gap between those two.

So the job is to make the interface an engineering artifact rather than a hope. That means getting output in a shape you can validate mechanically and treating a validation failure as a retry rather than a crash, accounting for cost and latency as first-class numbers, and measuring prompt quality on a small labelled set instead of eyeballing a few examples and declaring victory. Those three, structured output, cost, and measured prompting, are the spine of the session.

## Learning objectives

By the end of this session you should be able to:

- Call a hosted LLM API robustly and account for cost and latency as first-class engineering metrics.
- Get validated, schema-constrained output out of an LLM and handle the cases where it fails.
- Apply a disciplined prompting method and measure prompt quality on a small labeled set.

## The request and response interface

```{index} system prompt, user message, streaming
```

Strip away the SDK and every hosted chat model exposes the same shape of request. You send a list of **messages**, each tagged with a role. The **system prompt** sets the model's standing instructions and persona for the whole exchange, the **user message** carries the actual input, and prior assistant turns can be replayed to give the model the conversation so far. You set a cap on how many tokens the model may generate, commonly called `max_tokens`, along with the **temperature** that controls how random the sampling is, and optional stop conditions that end generation early. The response comes back with the generated text and, importantly, a usage record: how many tokens went in, how many came out, and increasingly how many were served from cache. That usage block is the meter, and reading it on every call is the difference between knowing what your pipeline costs and finding out at the end of the month.

Two settings deserve a moment because they trade against each other. Temperature near zero makes the model close to deterministic, which is what you want for extraction, where there is a right answer and creativity is a bug. Higher temperature is for generation tasks where variety helps. The token cap interacts with latency: the model streams tokens one at a time, so a larger `max_tokens` and a longer answer mean a longer wait, and a response can be delivered all at once when it finishes or **streamed** token by token as it is produced. Streaming does not make the total faster, it makes the first token arrive sooner, which matters for anything a human is watching and matters not at all for a batch job filling a table overnight.

The interface is deliberately similar across providers, which is why this course stays provider-agnostic: pick one hosted API, learn the shape, and the concepts move. What does not move, and what will break your code six months from now, is the specifics. Model identifiers, context limits, and prices all change on the provider's schedule, not yours. The defensive habit is to **pin the exact model ID you used** in your code and your report, and to read the current documentation for limits and pricing rather than trusting a number you memorized last term. This session quotes concrete prices to make the arithmetic real, and every one of them is stamped with the date it was true.

## Getting structured output you can trust

```{index} structured output, JSON Schema, tool calling, Pydantic
```
```{index} pair: failure mode; hallucinated field
```

The naive way to get structured data from a model is to ask for JSON in the prompt and hope. It mostly works and fails exactly often enough to corrupt a batch job: a stray sentence of preamble before the JSON, a trailing comma, a field the model decided to rename. The modern APIs give you two better routes, and both start from the same idea, which is to hand the model a **schema** and constrain it rather than ask politely.

The first route is **schema-enforced JSON**. You supply a JSON Schema describing the object you want, and the provider constrains decoding so the returned text parses and conforms. As of August 2026 this is Anthropic's `output_config.format` with a `json_schema` type (which replaced an earlier top-level `output_format` parameter) and OpenAI's `text.format` with `strict: true` on the Responses API. The second route is **tool calling**, sometimes called function calling, where you declare a tool with a typed argument schema (Anthropic's `input_schema`, and a `strict` flag to force exact adherence) and read the arguments the model produces for it. Structured-output mode and tool calling are close cousins: both send the model a schema and get back a payload shaped to it. Tool calling is the older and more universal path and doubles as the mechanism for agents; dedicated structured-output mode is newer and reads more directly for pure extraction.

Neither route makes the content correct, and students routinely skip past that. A schema guarantees the shape: that `max_pressure_MPa` is present and is a number. It says nothing about whether the number is right, whether the units were converted, or whether the model invented it because the datasheet did not mention pressure. Schema conformance is necessary and nowhere near sufficient, so the schema is only the first check.

That is why the output goes through a validator. Define the target as a **Pydantic** model, a Python class whose typed fields the library checks at construction, and feed the model's payload into it. Pydantic will reject a string where a float belongs, a missing required field, or a value that fails a custom check you write, such as a pressure that must be positive or a temperature range whose low end is below its high end. The step that turns this from decoration into engineering is what you do when validation fails.

```python
from pydantic import BaseModel, field_validator

class Component(BaseModel):
    part_number: str
    material: str
    max_pressure_MPa: float | None      # None when the datasheet omits it
    mass_kg: float | None

    @field_validator("max_pressure_MPa")
    @classmethod
    def pressure_is_plausible(cls, v):
        if v is not None and not (0 < v < 1000):
            raise ValueError("pressure out of plausible range")
        return v
```

### Treat a validation failure as a repair loop

```{figure} figures/repair-loop.png
:alt: A flow diagram. Datasheet text flows into a schema-constrained LLM call, then into a Pydantic validate step. From validate, a green arrow labelled "valid" leads to a "valid record, parts table" box; a red arrow labelled "still invalid" leads to a "give up after N tries, flag" box; and an amber arrow loops back from validate to the LLM call, labelled "invalid: send the error back and ask it to fix".
:width: 100%

The extract, validate, repair loop. When schema validation fails, send the error message back to the model and ask it to correct its output; only after a small number of failed repairs do you give up and flag the document for a human rather than write a bad record.
```

When validation fails, the useful move is to send the model its own broken output together with the validator's error message and ask it to fix that specific problem. Models are good at this, because the error is concrete ("mass_kg: expected number, got string '2.3 kg'") and the fix is local. You cap the number of repair attempts so a genuinely unparseable datasheet cannot spin forever, and when the cap is reached you flag the document for a human rather than write a record you do not trust. A crash on the first malformed response throws away a document the model could have fixed on the second try; a silent accept of the malformed response writes garbage into the table. The repair loop is the middle path, and it is why the validator and the API call belong in one function together rather than in separate scripts.

## Context, cost, and latency

```{index} prompt caching, cost accounting
```
```{index} pair: failure mode; silent truncation
```

Cost on these APIs is close to linear in tokens, so it is predictable once you measure it, and invisible until you do. Read the usage block on every call, multiply by the current per-token prices, and log the cost per call and per document. A concrete anchor, dated August 2026 and certain to drift: a mid-tier model like Claude Sonnet 5 was 2 US dollars per million input tokens and 10 dollars per million output tokens. A one-page datasheet is perhaps a thousand input tokens and a few hundred output, so a call costs a fraction of a cent, but a batch of ten thousand datasheets is real money, and a careless design that resends a large fixed context on every call multiplies it.

That last case is where **prompt caching** earns its keep. When many calls share a large, unchanging prefix, a long instruction block, a schema, a set of few-shot examples, a reference table, you can mark that prefix as cacheable and the provider stores its processed form. The first call pays a small premium to write the cache (on Anthropic, 1.25 times the normal input price for the short-lived cache) and every later call that reuses the prefix reads it at a steep discount (one tenth of the input price), for as long as the cache lives, which defaults to a few minutes and can be extended. The savings compound with reuse.

```{figure} figures/prompt-caching.png
:alt: A line chart of cumulative cost in US cents against the number of calls that reuse the same 20,000-token context, from 1 to 30. The grey "no caching" line rises steeply and linearly to about 132 cents; the red "prompt caching" line rises much more slowly to about 29 cents. An annotation reads "4.6x cheaper at 30 calls".
:width: 100%

Cost of reusing one 20,000-token context across many calls, with and without prompt caching, computed from Anthropic Sonnet 5 pricing on 2026-08-18. Caching turns a per-call cost into a one-time write plus a tenth-price read, so by 30 calls it is about 4.6 times cheaper. The break-even is at the second call. Providers change these multipliers, so treat the shape as the lesson and the numbers as a snapshot.
```

The other lever is choosing the right model and the right amount of context. A small, fast, cheap model is often perfectly good at an easy subtask like classifying a line or normalizing a unit, and reserving the large model for the hard reasoning is a real cost and latency win. And more context is not free even when it fits.

### The middle of a long context is where answers go to die

```{index} pair: failure mode; lost in the middle
```

The instinct when a task feels hard is to give the model more: stuff every possibly-relevant page into the prompt and let it sort them out. [Liu and colleagues (2023)](https://arxiv.org/abs/2307.03172) measured what that actually does. They gave models a question and many documents, only one of which held the answer, and moved the position of that relevant document through the context. Performance was not flat. It was U-shaped: highest when the answer sat at the very beginning or the very end of the context, and markedly worse when it sat in the middle.

The magnitudes are large. For GPT-3.5-Turbo answering over twenty documents, accuracy was 75.8% when the answer was first, 63.2% when it was last, and 53.8% when it was buried in the middle, a swing of 22 points driven by nothing but position. The middle number is below 56.1%, which was the model's closed-book accuracy with no documents at all. In other words, for a question whose answer was sitting right there in the context, burying it in the middle left the model worse off than giving it no documents at all. Stuffing everything into a long prompt is not a substitute for putting the right thing in the right place.

The failure that will actually bite you first, though, is cruder. A document that exceeds the context window does not always error. Depending on the provider and how you call it, the overflow can be silently dropped, and you extract from a truncated input without knowing it. **Count the tokens of every input before you send it,** using the provider's own tokenizer, and treat "this document is too long" as a case to handle rather than a possibility to ignore.

## Prompting you can measure

```{index} zero-shot prompting, few-shot prompting
```

Prompting has a reputation as a dark art, and it stays one only as long as you refuse to measure it. The techniques themselves are mundane. Give the model a clear role and explicit instructions in the system prompt. Decide between **zero-shot prompting**, just the instruction, and **few-shot prompting**, the instruction plus a handful of worked examples, and use few-shot when the format is fiddly or the task is easy to misread, which extraction usually is. Ground the model in the provided text and instruct it explicitly to say "not found" rather than invent, because a model told only to fill in the fields will fill them in whether or not the datasheet supports it. Ask for the source span when you can, so a human can check the extraction against the document. And hold temperature low, because extraction has a right answer.

What turns these from folklore into engineering is a **gold set**. Build a small set of examples, ten to thirty is plenty to start, where you have written down the correct extraction by hand. Then score any prompt against it automatically: field-level accuracy, how many of the fields across the set the prompt got exactly right. Now a prompt change is an experiment with a number attached. "The improved prompt raised field accuracy from 71% to 89% and cost 4% more per document" is a sentence you can act on; "the new prompt seems better" is not. The gold set is small enough to build in an afternoon and it is the single habit that most separates people who ship reliable extractors from people who tweak prompts forever. The demo builds one and shows the accuracy and cost deltas side by side, because a prompt that is more accurate and ten times more expensive is a different decision from one that is more accurate and free.

## Reliability engineering

```{index} retry with backoff
```

The remaining failures are the ordinary ones of any networked service, and the LLM API is a networked service. Calls hit rate limits and return 429s, servers return transient 5xxs, and connections time out. The standard answer is a **retry with backoff**: on a retryable error, wait a short and increasing interval, with a little randomness so a fleet of workers does not retry in lockstep, and cap the attempts. Make the operation **idempotent** where you can, so a retry that actually did succeed the first time does not double-charge or double-write. Log every call's prompt, response, and usage, reusing the same tracking discipline the course applied to experiments earlier, because when an extraction is wrong in week nine the log is the only way to find out whether the prompt, the model, or the datasheet changed. And never truncate an input silently to make it fit; count first, and handle the overflow deliberately.

## Where this pushes back

```{index} pair: failure mode; schema-valid but wrong
```

The honest limitations of this interface are mostly the ways its guarantees are narrower than they look. Schema-constrained output guarantees shape, not truth: a record can be perfectly valid and factually wrong, with a hallucinated pressure or a unit left unconverted, and no validator catches it unless you encode the check. The units-and-numbers problem is where extraction quietly fails most often, because "2.5" as a string and 2.5 as a float and 2.5 bar versus 2.5 MPa all look nearly identical and mean different things; put explicit units in the schema and a normalization step after it. Non-determinism undermines debugging, because a prompt that worked once may fail the next time, so "it worked in the demo" is not a passing test and low temperature plus a fixed gold set is how you get repeatability. Cost is invisible unless you make it visible, and a pipeline without per-call usage logging cannot be reasoned about. And the whole interface drifts underneath you: model IDs are retired, context limits and prices change, and the very structured-output parameters this session names have already moved once, which is why the durable skill is reading the current documentation and pinning what you used, not memorizing a parameter.

There is a deeper limit. Everything here makes an LLM call reliable and measurable; none of it makes the model know something it was not given. When the answer is not in the prompt, a better schema and a lower temperature will not conjure it, and stuffing more context invites the lost-in-the-middle failure above. The fix for that is retrieval.

## In-class demo

The notebook [`l16-structured-extraction.ipynb`](l16-structured-extraction.ipynb) builds the extractor end to end on a handful of small component datasheets, including a deliberately incomplete one. It defines the `Component` Pydantic schema, sends a datasheet with a schema-constrained request, validates the result, and runs the repair loop when validation fails, printing token usage and the estimated cost of each call. It then does the two things the session argues for: on the datasheet that omits pressure, it shows the model returning `null` rather than a hallucinated number when the prompt tells it to, and it scores a naive prompt against an improved one on a small gold set, printing the accuracy delta beside the cost delta. The notebook is built to run for everyone: with no API key it uses a deterministic stand-in that returns provider-shaped responses, so the schema, validation, repair loop, cost accounting, and gold-set scoring all execute offline, and with a key set it makes the same calls against a real provider. The moments to watch are the repair loop turning a rejected response into a valid one, and the incomplete datasheet producing a null instead of a confident fabrication.

## Summary

The lesson of this session is that a hosted LLM is a system component like any other, with a cost, a latency, a failure model, and an output you must validate before you trust it. Getting structured data out of one reliably takes a loop: constrain the output to a schema, validate it against a typed model, and repair rather than crash when it fails. Cost and latency are numbers you read off every response and design around, with prompt caching and model choice as the main levers, and prompting stops being guesswork the moment you score it against a small gold set. Above all, a schema guarantees shape and never truth, so the units, the "not found" behavior, and the gold set are the checks that keep the parts table honest.

## Resources

- [Liu et al., "Lost in the Middle: How Language Models Use Long Contexts" (2023)](https://arxiv.org/abs/2307.03172). Why more context is not free; the source of the U-shaped accuracy figure. Published in TACL 2024.
- [Anthropic structured outputs guide](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) and [tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview). The two routes to schema-shaped output; read the current version, since these parameters have already changed once.
- [OpenAI structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs). The other provider's take, for the cross-provider view; note the canonical shape moved from Chat Completions to the Responses API.
- [Anthropic prompt caching guide](https://platform.claude.com/docs/en/build-with-claude/prompt-caching). The cache-write and cache-read multipliers behind the cost figure, and the minimum cacheable length.
- [Pydantic documentation: models](https://docs.pydantic.dev/latest/concepts/models/) and [validators](https://docs.pydantic.dev/latest/concepts/validators/). Defining the schema and writing field- and model-level checks.
- [JSON Schema](https://json-schema.org/). The vocabulary both providers' structured-output modes speak; current specification is 2020-12.
- [Anthropic prompt engineering overview](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/overview). Provider guidance on the prompting techniques above; read alongside your own provider's guide.

## Assignment

Assignment 8, structured extraction from engineering documents, was released last session and is due about a week later. It asks you to build and evaluate a schema-constrained LLM extractor that turns messy engineering text into a validated, normalized table, with per-call cost logging and a small gold set to measure prompt quality, which is exactly the pipeline this session builds in miniature. This page does not restate the rubric.
