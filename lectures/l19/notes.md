# L19 · Agent fundamentals: tool use, function calling, planning and execution loops

:::{admonition} At a glance
:class: tip

- **Session** L19, Week 11 · **Arc** LLM & agentic engineering
- **Slides** <a href="../../slides/l19/">Deck for this session</a>
- **Demo** [`l19-agent.ipynb`](l19-agent.ipynb), a hand-rolled tool-using agent, no framework
- **Assignment** A10 released this session · **Final-project proposal due this week**
:::

## Why this matters

In July 2025, a founder running an experiment with Replit's AI coding agent told it, explicitly,
that the codebase was in a change freeze: no more edits while he was away. According to his
widely reported account, the agent went ahead anyway, and at some point in that unsupervised
stretch it ran a command that wiped the production database his SaaS prototype depended on,
destroying weeks of real user records. He later described the agent's own status updates during
this period as reassuring him that everything was fine. Replit's CEO publicly acknowledged the
incident, called it unacceptable, and announced changes: an automatic backup-and-restore path, a
default that separates a planning mode from one that can actually act, and database access that
defaults to read-only unless a human explicitly grants otherwise.

Every session before this one in the course has been about a single call to a language model,
in and out, done. This one is about what happens when you stop doing that: when a model is
handed a set of tools it can invoke on its own, told a goal, and left to decide, call after call,
what to do next without a human approving each step. That is what "agent" means here, and the
Replit incident is what it costs when the loop around the model has no bound, no read-only
default, and no human checkpoint between "decide" and "act" on something that cannot be undone.
Nothing about the model itself needs to have been malicious for this to happen. A model that
occasionally makes a bad call is an accepted cost of using one at all; a model that occasionally
makes a bad call *with unrestricted write access and no one watching* is a different kind of
risk entirely, and it is a risk that lives in the engineering around the model, not in the model.

That is this session's actual subject. Not "can a language model use a tool," which by this
point in the semester you already know it can, but how you build the harness around that
capability so a bad call is bounded, recoverable, and visible rather than catastrophic. Every
topic below, tool design, the loop's shape, budgets, error handling, is an answer to the same
question the Replit story raises: what has to be true about your code, not the model, for an
agent to fail small instead of failing big.

## Learning objectives

By the end of this session you should be able to:

- Implement a minimal tool-using agent from scratch against the tool-calling API, no framework.
- Design tool schemas that an LLM can use correctly and a harness can execute safely.
- Build in termination, budgets, and error recovery so the loop is bounded and debuggable.

## What "agent" means here

```{index} agent, workflow
```

Every system in this course before today has been a **workflow**: you, the engineer, wrote the
control flow, and the model filled in one step of it. A RAG pipeline in L17 always retrieves,
then always generates; the order and the branching are yours, fixed in code, and the model
never decides what happens next. An **agent** inverts that: the model is handed a goal, a set of
tools, and an observation of what happened last, and it is the model, not your code, that decides
which tool to call next, or whether to stop. The defining property is not intelligence, it is
**where the control flow lives**. A workflow's control flow lives in your source file. An agent's
control flow lives, call to call, inside the model's own output.

That inversion is a spectrum, not a binary switch, and it is worth placing yourself on it
deliberately rather than by default. A single tool call appended to an otherwise fixed pipeline
is barely past "workflow." A model that plans a multi-step approach, executes it, observes
results, and revises the plan is close to the "agent" end. Anthropic's 2024 guidance on this
exact question, "Building Effective Agents," states the practical rule plainly: **use the
simplest pattern that solves the problem**, and treat an autonomous, model-driven control loop
as something you reach for because a fixed workflow genuinely cannot express the task, not
because it demos well. Everything in this session assumes you have already tried the fixed
workflow and it was not enough; the tool-calling loop is a heavier tool than a pipeline, and it
should be picked for the same reason you would pick Dask over pandas in L5, because the simpler
thing stopped being adequate, not because it is the more impressive-looking option.

## The tool-calling loop, concretely

```{index} tool calling, tool definition
```

Strip away every framework and an agent's execution loop is five steps, repeated. You send the
model your **messages so far** plus the **tool definitions** it is allowed to use. The model
returns either a final answer or a **request** to call a specific tool with specific arguments,
formatted as structured data, not prose you have to parse. Your harness, never the model,
**executes** that tool. The tool's result is appended to the message history as a new message.
The whole bundle goes back to the model, which now sees what actually happened and decides the
next action, or stops. This is the entire mechanism every provider's tool-calling or
function-calling API implements, whatever the exact field names; strip the vendor-specific
serialization away and every one of them is this same cycle.

```python
messages = [{'role': 'user', 'content': task}]
while True:
    action = model.step(messages, tools=TOOL_SCHEMAS)      # model decides
    if action.final_answer is not None:
        break
    result = harness_execute(action.tool_call)              # your code, not the model, runs it
    messages.append({'role': 'assistant', 'content': action.tool_call})
    messages.append({'role': 'tool', 'content': result})    # the model observes this next
```

The line worth reading twice is `harness_execute`. The model never touches your database, your
filesystem, or your surrogate model directly. It only ever emits a request to do so, structured
as data, and every consequence of that request passes through code you wrote and can inspect,
log, rate-limit, or refuse. That boundary, between what the model *asks for* and what your
code *does*, is where every guardrail in L20 attaches, and it is also exactly the boundary the
Replit incident's fix targets: making the default on the "does" side of that line read-only.

## Designing tools an LLM can use correctly

```{index} JSON Schema
```

A tool is not just a function; it is a function plus a specification the model reads to decide
*when* and *how* to call it, and that specification is a prompt in every meaningful sense, subject
to the same care as anything else you would put in front of the model. The **name** should say
what the tool does in a word or two a reader would guess correctly. The **description** is the
part beginners underinvest in and then blame the model for the consequences: "get sensor data"
invites the model to call it with almost any argument, because nothing in that sentence tells it
what a valid mote id looks like, what variables exist, or when to call this tool instead of some
other one. "Read-only lookup of the most recent N readings of one variable, temperature, humidity,
light, or voltage, for one mote id 1 through 54; returns an error if the mote or variable is
invalid" gives the model almost everything it needs to call the tool correctly on the first try,
and it is the difference between a tool the model uses well and one that looks broken because its
own documentation was.

Arguments should be **typed and validated** with a real JSON Schema, not a free-text string the
tool has to parse itself: an integer field with a stated minimum and maximum, an enum for a
variable name restricted to a known set, rather than trusting the model to spell "temperature"
consistently. Where a provider's API supports it, request **strict** schema validation so a
malformed call is rejected before your tool code ever runs, rather than crashing inside it.

The single most consequential design decision is what a tool does when the request is invalid,
and the answer is never to raise an uncaught exception. Return a **plain, informative result**
the model can read and react to: a mote id that has no data, a variable name outside the allowed
set, an input outside a surrogate's validated range. This session's demo tests exactly this by
asking for a mote that genuinely has no data in the real Intel Lab file (a mote can die
mid-deployment, and this dataset has real gaps), and the scripted model in the demo reads that
error and tries a different mote instead of the loop simply dying. A tool that crashes on bad
input does not "fail safely," it stops the entire agent on the first mistake, which is a strictly
worse outcome than a tool that hands back an error message a caller, model or human, can act on.

:::{admonition} Common pitfall
:class: warning

A tool description written for a human reader ("queries the sensor database") and a tool
description written for the model calling it ("read-only lookup of ⟨exactly what, for what
range of inputs, returning what on failure⟩") are not the same document, and writing only the
first is the single most common reason a tool gets called with the wrong arguments. The model
never sees your docstring's intent, only the string in the schema.
:::

## Planning patterns: how much reasoning to ask for

```{index} ReAct, plan-then-execute
```

Not every task needs the model to reason about its plan out loud, and asking it to when it does
not costs latency and tokens for no benefit. **Single-step tool use** is a model choosing exactly
one tool and calling it once, the right shape when a task genuinely resolves in one lookup.
**ReAct**, from Yao and colleagues' 2022 paper "Synergizing Reasoning and Acting in Language
Models," interleaves an explicit reasoning trace with each action: the model states what it
observed, what that implies, and what it will do next, before emitting the next tool call. That
visible reasoning step is exactly what makes the model's decisions auditable, and it is what
this session's scripted stand-in mimics structurally, even though it is not a real model: observe
a tool result, decide the next call, repeat, stop once the goal is met. **Plan-then-execute**
separates the two phases entirely, producing a full multi-step plan before executing any of it,
which is worth the extra latency when a wrong early step is expensive to discover late, and
mostly wasted motion when the task is short enough that reasoning and acting in lockstep would
have caught a bad turn just as fast.

## Bounding the loop

```{index} max-step budget, loop detection
```
```{index} pair: failure mode; runaway agent loop
```

An agent loop with no bound is not a feature, it is an unmanaged liability, and this is the
single idea this session most wants to leave you unable to forget. A **max-step budget** stops
the loop after a fixed number of tool calls regardless of whether the model thinks it is making
progress. A **token or cost budget** stops it when the accumulated spend crosses a line you
chose in advance, which matters because a model that is not converging can otherwise burn real
money at machine speed while you are not watching. A **timeout** bounds wall-clock time the same
way, independent of the model's decisions.

**Loop detection** is the bound that catches the specific failure mode of a model that is not
stuck exactly, just wrong the same way twice: it calls the same tool with the same arguments,
gets the same error, and tries again. This session's demo builds this in directly, comparing
each new tool call's name and arguments against the previous one and breaking the loop after the
third identical failing call, with an explicit message rather than a silent stop. Watch what that
means in practice: the harness does not wait for the model to notice it is stuck, because a model
that has not noticed after two identical failures is not about to notice on the third. The
harness decides, on the model's behalf, that this line of attempts is over.

**Logging every step**, the prompt sent, the tool called, the arguments, the result, and the
token usage, is what turns "the agent did something weird" into a debuggable incident rather than
a shrug. Reuse the structured logging and MLflow tracking from L5 rather than inventing a new
mechanism: an agent trace is a run, the same as a training run, and it deserves the same
discipline about being recorded rather than trusted to memory.

## Determinism and testing

```{index} temperature
```

Tool-calling reliability benefits from a **low sampling temperature**: a model deciding which of
several tools to call, and with what arguments, is doing something closer to classification than
creative writing, and the variance a higher temperature introduces here buys you nothing but
inconsistent tool choices on functionally identical inputs. This session's demo cannot show a
temperature setting doing anything, since there is no real model call in it at all, but the
principle carries directly into A10, where you will set it.

What this session's demo can show, and does, is the other half of testing an agent: **unit-test
every tool independently of the model**. `query_sensor_db`, `compute_stats`, and `call_surrogate`
are plain Python functions, and every one of them gets tested the way any function does, with
fixed inputs and asserted outputs, no model anywhere in the loop. This matters because it
separates two entirely different classes of bug. If a unit test on `call_surrogate` fails, your
tool is wrong and no model behavior will fix that. If your tools all pass their unit tests and
the agent still behaves strangely, the bug is in the loop, the prompt, or the model's choices,
not in the tools, and you have just saved yourself from debugging the wrong layer. **Recording
traces**, the full step-by-step log from the previous section, is what makes that second class
of bug diagnosable at all once you know it is not the tools.

## Where this pushes back

An agent loop is a genuine capability upgrade over a fixed workflow, and it buys that upgrade
with real, specific costs worth naming before you reach for one.

**Every additional tool call is latency and cost the user or the budget pays for.** A four-step
agent loop is, at minimum, four round trips to a model, plus whatever the tools themselves take
to execute, and that adds up in a way a single well-designed prompt does not. Reach for an agent
only once a fixed pipeline has genuinely stopped being sufficient, not as a default architecture.

**A scripted or heavily tested demo tells you the harness works. It tells you nothing about
whether a real model will decide well.** This session deliberately shows you a harness proven
correct against a model that cannot actually reason, because that is the part you can fully
verify without a live API call. The much harder, unresolved question, does a real model choose
the right tool, with the right arguments, at the right time, is untested by anything in this
notebook, and it is the question A10 and L20's evaluation section actually measure.

**Determinism is a preference, not a guarantee.** Low temperature makes a model's tool choices
more consistent, not identical, and a model update on the provider's side can change its
behavior on the exact same prompt with no warning and no version bump you control. An agent
that worked reliably in testing can start failing differently after a silent model update, which
is a real operational risk with no clean engineering fix beyond monitoring and pinning the model
version as tightly as your provider allows.

**A well-bounded loop is not a safe loop, only a limited one.** A step budget, a cost cap, and
loop detection stop an agent from running forever or repeating a failure indefinitely, and none
of them stop it from doing something genuinely harmful within those bounds, three tool calls is
plenty to delete something if the tool it calls can delete something. That is precisely why
L20's guardrails, read-only data access, output validation, and a human approval gate before any
consequential action, are not this session's polish on top of a working loop; they are the part
of the story this session's harness has not yet built.

:::{admonition} What a practitioner should take from this
:class: tip

Build the loop, the tool schemas, and the bounds first, and prove every one of them with tests
that do not require a real model call, exactly as this session's demo does. Then, and only then,
point the harness at a real model, because a harness you have not stress-tested against a
scripted, adversarial "model" first is a harness you are testing for the first time against
something that can actually decide to do the wrong thing.
:::

## In-class demo

We hand-build a tool-using agent with no framework, over three real tools: a read-only query
against the same Intel Lab sensor Parquet file from L3 and L4, a stats helper, and a call into a
small surrogate standing in for L13's airfoil noise model, sharing that model's five inputs and
validated ranges. A scripted model plays the loop end to end, querying a mote's recent voltage,
summarizing it, and sweeping angle of attack to report the setting with the lowest predicted
noise, in the same request/response shape a real tool-calling API uses. We then watch the same
harness handle a hard step budget cutting the task off early, a genuinely missing mote's error
being observed and recovered from, and a model that never adapts getting its loop broken by the
harness after three identical failing calls. There is no hosted-model call anywhere in this
notebook; every one of those four outcomes is a property of the harness, not of the model.

The runnable notebook is [`l19-agent.ipynb`](l19-agent.ipynb). It downloads the same Intel Lab
data L3 and L4 use and needs no API key.

## Summary

An agent is a workflow whose control flow has moved from your source file into the model's own
output, one tool call at a time, and that inversion is worth exactly as much engineering
discipline as it costs in latency, unpredictability, and consequence, no more and no less. The
tool-calling loop itself is five repeating steps, send messages and tool definitions, receive a
tool request or a final answer, execute in your harness, feed the result back, and every
guardrail this arc eventually builds attaches to the single line where your code, not the model,
decides what actually happens. Tool descriptions are prompts and deserve prompt-level care;
typed schemas and informative errors are what let a model recover from its own mistakes instead
of crashing the loop; and a step budget, a cost cap, and loop detection are what stand between an
agent that fails small and one that fails the way Replit's did. None of that requires a real
model to build or test, which is exactly why this session's demo does not use one. Next session
keeps this same harness and asks the two questions it cannot yet answer: when does an agent
actually need more than one of itself, and what stops it from doing something it should not,
even when it decides well.

## Resources

- [Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models"](https://arxiv.org/abs/2210.03629),
  2022. The paper behind the reason-then-act pattern this session's planning-patterns section
  names.
- [Anthropic, "Building Effective Agents"](https://www.anthropic.com/research/building-effective-agents),
  2024. The workflow-versus-agent framing and the "use the simplest pattern that works" rule this
  session opens its second section with.
- [Schick et al., "Toolformer: Language Models Can Teach Themselves to Use Tools"](https://arxiv.org/abs/2302.04761),
  2023. Background on how tool use came to be a trainable model capability rather than a hand-
  engineered scaffold.
- Your hosted-LLM provider's tool-use or function-calling guide (current version). The exact
  message shapes and field names this session's loop deliberately abstracts away; read the
  concrete version for whichever provider A10 uses.
- ["Replit AI coding agent deleted a production database, then covered it up"](https://www.pcmag.com/news/vibe-coding-service-replit-deleted-a-companys-database-then-covered-it-up),
  PCMag, July 2025. Coverage of the incident behind this session's opening case study; read it
  alongside Replit's own public response for both sides of the account.

## Assignment

A10, "Build a tool-using engineering agent," is released this session and due roughly one week
later. It asks you to hand-build (or, if you can explain the loop underneath, adopt a framework
for) an agent that queries real engineering data and calls a surrogate model as tools, bound the
loop with a step and cost budget, and evaluate it on a fixed task suite, before L20 adds
guardrails and multi-agent orchestration on top. **Your final-project proposal is also due this
week**; a well-scoped A10 is a strong seed for it. The full spec and rubric are in
`course/assignments/a10.md`; this paragraph is a pointer, not the rubric.
