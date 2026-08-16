---
marp: true
theme: course
paginate: true
header: "06-763 · L19"
footer: "Systems & Toolchains for AI in Engineering"
---

<!-- _class: title -->

# L19 · Agent fundamentals

## Week 11 · LLM & agentic engineering

**Systems & Toolchains for AI in Engineering**

---

## Roadmap

1. Why this matters: an agent, a code freeze, a deleted database
2. What "agent" means here
3. The tool-calling loop, concretely
4. Designing tools an LLM can use correctly
5. Planning patterns
6. Bounding the loop
7. Determinism and testing
8. Live demo: a hand-rolled agent, no framework

<!-- 110 min. Budget roughly 10/15/15/15/10/15/10/20 demo.
     No hosted LLM call in the demo -- no API key, no network path to a
     provider in the build environment. The scripted stand-in is explicit
     about this, twice. If running long, cut the planning-patterns slides,
     not the demo. -->

---

<!-- _class: section -->

# Why this matters

---

## A code freeze

July 2025. A founder tells Replit's AI coding
agent: **no more edits** while he's away.

The agent had database access, and a goal.

---

## What happened next

Widely reported: the agent ran a command
that wiped the **production database**.

Weeks of real user data, gone.

---

## The part that makes it worse

According to the account: the agent's own
status updates said everything was fine.

Replit's CEO publicly acknowledged the incident.

[PCMag, July 2025](https://www.pcmag.com/news/vibe-coding-service-replit-deleted-a-companys-database-then-covered-it-up)

---

## The fix Replit announced

Automatic backup/restore. A **planning** mode
separated from an **acting** mode.

Database access **read-only by default**,
unless a human explicitly grants otherwise.

---

## What's different about today's session

Every session so far: one call to a model, in and out, done.

Today: a model that **decides**, call after call,
what to do next. No human approving each step.

---

## Nothing about the model needs to be malicious

A model that occasionally makes a bad call
is an accepted cost of using one at all.

A model that makes a bad call **with unrestricted
write access and no one watching** is different.

---

## This session's actual subject

Not "can a model use a tool." You already know it can.

**How do you build the harness** so a bad call
is bounded, recoverable, and visible, not catastrophic.

---

<!-- _class: section -->

# What "agent"
## means here

---

## Workflow vs. agent

**Workflow**: you write the control flow.
The model fills in one step.

**Agent**: the model decides what happens next,
call to call, from inside its own output.

---

## The defining property

Not intelligence.

**Where the control flow lives**:
your source file, or the model's output.

---

## A spectrum, not a switch

One tool call bolted onto a fixed pipeline:
barely past "workflow."

A model that plans, executes, observes,
revises: near the "agent" end.

---

## The rule from Anthropic's own guidance

"Building Effective Agents," 2024:

> Use the **simplest pattern** that solves the problem.

Reach for an autonomous loop because a fixed
workflow genuinely can't express the task.

---

## Not because it demos well

Same logic as Dask over pandas in L5:

Pick the heavier tool because the simpler one
**stopped being adequate.** Not by default.

---

<!-- _class: section -->

# The tool-calling loop
## concretely

---

## Five steps, repeated

1. Send messages + tool definitions
2. Model returns a tool request, or a final answer
3. **Your harness** executes the tool
4. Result appended as a new message
5. Repeat, or stop

---

## In code

```python
messages = [{'role': 'user', 'content': task}]
while True:
    action = model.step(messages, tools=TOOL_SCHEMAS)
    if action.final_answer is not None:
        break
    result = harness_execute(action.tool_call)  # your code
    messages.append({'role': 'assistant', 'content': action.tool_call})
    messages.append({'role': 'tool', 'content': result})
```

---

## The line worth reading twice

`harness_execute`.

The model never touches your database directly.
It only ever **asks**.

---

## Where every guardrail attaches

The boundary between what the model **asks for**
and what your code **does**.

Replit's fix: make the default on the "does"
side read-only.

---

<!-- _class: section -->

# Designing tools
## an LLM can use correctly

---

## A tool is a function *plus a prompt*

The description is what the model reads
to decide **when** and **how** to call it.

Vague description → wrong-argument calls that
look like "the model is dumb." It's a spec bug.

---

## Bad vs. good, side by side

| Bad | Good |
|---|---|
| "get sensor data" | "Read-only lookup of the most recent N readings of one variable (temperature/humidity/light/voltage) for mote 1-54; errors on invalid input" |

---

## Type and validate every argument

JSON Schema: integer with min/max, enum for a
restricted variable name.

Not a free-text string the tool has to parse
itself. Request `strict` validation where supported.

---

## The most consequential design decision

What does a tool do on invalid input?

**Never** an uncaught exception.
**Always** a plain, informative result.

---

## Why: a crash stops the whole agent

A missing mote, an out-of-range input:
return an error the model can read and react to.

A tool that crashes doesn't fail safely.
It fails the *entire* loop, on the first mistake.

---

## The pitfall

A description written for a human reader
≠ a description written for the model calling it.

The model never sees your docstring's intent.
Only the string in the schema.

---

<!-- _class: section -->

# Planning
## patterns

---

## Single-step tool use

One tool, called once. The right shape
when the task genuinely resolves in one lookup.

---

## ReAct: reason, then act

Yao et al., 2022: interleave a visible reasoning
trace with each action.

Observe → what does this imply → decide the
next call. Auditable, one step at a time.

[arxiv.org/abs/2210.03629](https://arxiv.org/abs/2210.03629)

---

## Plan-then-execute

Produce the **full plan** before executing any of it.

Worth the latency when a wrong early step
is expensive to discover late.

---

## When explicit planning is wasted motion

Short tasks, where reasoning and acting in
lockstep would've caught a bad turn just as fast.

---

<!-- _class: section -->

# Bounding
## the loop

---

## An unbounded loop is not a feature

It's an unmanaged liability.

The single idea this session most wants you
to not be able to forget.

---

## Four kinds of bound

**Max-step budget**: stop after N tool calls
**Cost/token budget**: stop at a dollar line
**Timeout**: bound wall-clock time
**Loop detection**: stop a model repeating itself

---

## Loop detection, specifically

Same tool. Same arguments. Same error. Again.

The harness compares each call to the last one
and breaks after the third identical failure.

---

## The harness decides, not the model

A model that hasn't noticed it's stuck after
two identical failures won't notice on the third.

---

## Log every step

Prompt, tool call, arguments, result, token usage.

Reuse L5's structured logging / MLflow.
An agent trace is a run, same as a training run.

---

<!-- _class: section -->

# Determinism
## and testing

---

## Low temperature for tool selection

Choosing which tool, with what arguments,
is closer to classification than creative writing.

Higher temperature buys inconsistent choices
on identical inputs. Nothing else.

---

## Unit-test every tool, independently of the model

Plain Python functions. Test them the way
you test any function. No model in the loop.

---

## Why this separation matters

Tool fails its unit test → the tool is wrong.
No model behavior fixes that.

Tools all pass, agent still weird →
bug's in the loop, the prompt, or the model's choices.

---

## Record traces

Without the full step-by-step log,
that second class of bug is not diagnosable.

---

<!-- _class: section -->

# Where this
## pushes back

---

## Every tool call is latency and cost

A 4-step loop = at minimum 4 round trips to a
model + whatever the tools themselves take.

Reach for an agent once a pipeline has
genuinely stopped being enough. Not by default.

---

## A working demo proves the harness, not the model

This session's demo is provably correct against
a model that **cannot reason at all**.

Does a real model choose well? Untested here,
that's A10 and L20's evaluation section.

---

## Determinism is a preference, not a guarantee

Low temperature: more consistent, not identical.

A silent provider-side model update can change
behavior on the exact same prompt. No version bump.

---

## A bounded loop is a limited loop, not a safe one

A step budget stops it running forever.

It does not stop it doing something harmful
**within** those bounds. 3 calls is plenty to delete something.

---

## What a practitioner should take from this

Build the loop, the schemas, the bounds first.
Prove them without a real model call.

**Then** point the harness at a real model,
not before you've stress-tested it against a hostile script.

---

<!-- _class: demo -->

# Demo

## `l19-agent.ipynb`

Hand-rolled agent, no framework. 3 real tools:
sensor query, stats, surrogate.

---

## What to watch

- The happy path: query → stats → sweep → answer, 7 real steps
- A tight budget: clean `budget_exhausted`, not a crash
- A missing mote: error observed, recovered from
- A stubborn model: harness breaks the loop after 3 identical failures

---

## Recap

- An agent moves control flow from your code into the model's output, one call at a time
- The loop is 5 steps; `harness_execute` is the line every guardrail attaches to
- Tool descriptions are prompts; vague ones cause "the model is dumb" bugs that are spec bugs
- Bound every loop: steps, cost, timeout, and repeated-failure detection
- Unit-test tools without a model; that's how you know which layer a bug is in

---

## Next

**Assignment** A10 released today, due ~1 week
**Also due this week**: final-project proposal
**Reading** Yao et al. 2022 (ReAct); Anthropic, "Building Effective Agents"
**L20** Multi-agent orchestration, frameworks, and the guardrails
this session's harness doesn't have yet

Full notes, with all sources: `lectures/l19/notes.md`
