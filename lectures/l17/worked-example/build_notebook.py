#!/usr/bin/env python3
"""Generate lectures/l17/l17-tiny-llm.ipynb, the L17 worked example.

A tiny GPT, trained from scratch on the text of this course's own lecture notes (Lectures 1 to
16, downloaded from the course site). The tokens are characters, the model is the transformer
of Lecture 12 with a causal mask, and the loss is next-token cross-entropy at every position of
every context window. It trains in about two minutes on a Colab GPU.

The code cells are the code on the slides, character for character. figures/make_figures.py
imports CELLS from this file, executes the notebook once with nbclient, and builds the figures
and the widget data from that same run, so the numbers in the notebook, the notes and the deck
agree.

    python3 lectures/l17/worked-example/build_notebook.py              # write the notebook, without outputs
    cd lectures/l17/figures && uv run --no-project --python 3.12 --with torch --with matplotlib \
        --with nbclient --with nbformat --with ipykernel --with tiktoken --with transformers \
        python make_figures.py tiny                     # execute it, and build the figures
    python3 tools/colab_setup.py --write "$PWD/lectures/l17/worked-example/l17-tiny-llm.ipynb"
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "l17-tiny-llm.ipynb"

CELLS = []


def md(text):
    CELLS.append({"cell_type": "markdown", "id": f"md-{len(CELLS) + 1:02d}", "metadata": {},
                  "source": text.strip("\n").splitlines(keepends=True)})


def code(text):
    CELLS.append({"cell_type": "code", "id": f"code-{len(CELLS) + 1:02d}", "execution_count": None,
                  "metadata": {}, "outputs": [], "source": text.strip("\n").splitlines(keepends=True)})


md("""
# L17 worked example: a tiny LLM, trained on our own lecture notes

A large language model (LLM) predicts the next token of a text, again and again. Here we build
the smallest version that still works:

- **The text:** the notes of Lectures 1 to 16 of this course.
- **The tokens:** single characters.
- **The model:** the transformer of Lecture 12, with a causal mask: each position sees only
  the past.
- **The training:** next-token prediction at every position of every context window.

About 0.8 million parameters. It trains in about two minutes on a GPU.

**On Colab:** Runtime > Change runtime type > GPU, before you run anything.
""")

md("""
## 1. Libraries and device
""")
code("""
import time
import urllib.request

import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import torch.nn.functional as F

if torch.cuda.is_available():
    device = "cuda"      # Colab: Runtime > Change runtime type > GPU
elif torch.backends.mps.is_available():
    device = "mps"       # a Mac with Apple silicon
else:
    device = "cpu"       # works, but about ten times slower
print("device:", device)
""")

md("""
## 2. The text: our lecture notes

The course site serves the source of every released lecture. We download Lectures 1 to 16, and
keep the prose, the math and the code; figures, index entries and HTML go.
""")
code("""
URL = ("https://kitchingroup.cheme.cmu.edu/f26-06763/"
       "_sources/lectures/l{:02d}/notes.md")


def clean(md):
    # keep prose, math and code; drop figures, index entries, boxes, HTML
    keep, skip = [], False
    for line in md.splitlines():
        if line.startswith("```{"):          # a directive: figure, index, ...
            skip = True
            continue
        if skip:
            skip = not line.startswith("```")
            continue
        if line.startswith((":::", ":class:", "<")):
            continue
        keep.append(line)
    return "\\n".join(keep)


text = ""
for n in range(1, 17):
    with urllib.request.urlopen(URL.format(n)) as r:
        text += clean(r.read().decode("utf-8")) + "\\n\\n"
print(f"{len(text):,} characters")
print(text[1000:1300])
""")

md("""
## 3. Tokens: one per character

Real LLMs use subword tokens (byte-pair encoding). Characters are the simplest tokenizer that
works: every distinct character gets an integer id.
""")
code("""
chars = sorted(set(text))
vocab_size = len(chars)
stoi = {c: i for i, c in enumerate(chars)}     # character -> token id
itos = {i: c for i, c in enumerate(chars)}     # token id -> character


def encode(s):
    return [stoi[c] for c in s]


def decode(ids):
    return "".join(itos[i] for i in ids)


print(vocab_size, "distinct characters")
print(encode("heat exchanger"))
""")

md("""
## 4. Context windows: the inputs, and the targets shifted by one

A **context window** is `block_size` characters in a row. The target at each position is the
character that comes next. One window of 128 characters is 128 next-token predictions.
""")
code("""
data = torch.tensor(encode(text))
n = int(0.9 * len(data))
train_data, val_data = data[:n], data[n:]     # last 10% held out

block_size = 128      # context window: characters the model sees at once
batch_size = 64       # windows per training step


def get_batch(split):
    d = train_data if split == "train" else val_data
    i = torch.randint(len(d) - block_size - 1, (batch_size,))
    x = torch.stack([d[j:j + block_size] for j in i])           # inputs
    y = torch.stack([d[j + 1:j + block_size + 1] for j in i])   # next chars
    return x.to(device), y.to(device)


x, y = get_batch("train")
print("input :", repr(decode(x[0, :40].tolist())))
print("target:", repr(decode(y[0, :40].tolist())))
""")

md("""
## 5. The model: the transformer of Lecture 12, with a causal mask

- `Block`: causal self-attention, then a small MLP, each with a residual connection.
- `is_causal=True`: position $t$ attends only to positions $1, \\dots, t$.
- `TinyGPT`: token and position embeddings, four blocks, and a final layer that gives one
  logit per token in the vocabulary.
""")
code("""
n_embd, n_head, n_layer = 128, 4, 4


class Block(nn.Module):
    # one transformer block: causal self-attention, then an MLP
    def __init__(self):
        super().__init__()
        self.ln1 = nn.LayerNorm(n_embd)
        self.qkv = nn.Linear(n_embd, 3 * n_embd)       # q, k, v at once
        self.proj = nn.Linear(n_embd, n_embd)
        self.ln2 = nn.LayerNorm(n_embd)
        self.mlp = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.GELU(),
            nn.Linear(4 * n_embd, n_embd),
        )

    def forward(self, h):
        B, T, C = h.shape
        q, k, v = self.qkv(self.ln1(h)).split(n_embd, dim=2)
        q, k, v = (t.view(B, T, n_head, C // n_head).transpose(1, 2)
                   for t in (q, k, v))
        a = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        h = h + self.proj(a.transpose(1, 2).reshape(B, T, C))
        return h + self.mlp(self.ln2(h))


class TinyGPT(nn.Module):
    def __init__(self):
        super().__init__()
        self.tok = nn.Embedding(vocab_size, n_embd)    # token -> vector
        self.pos = nn.Embedding(block_size, n_embd)    # position -> vector
        self.blocks = nn.Sequential(*[Block() for _ in range(n_layer)])
        self.ln = nn.LayerNorm(n_embd)
        self.head = nn.Linear(n_embd, vocab_size)      # vector -> logits

    def forward(self, x):
        T = x.shape[1]
        h = self.tok(x) + self.pos(torch.arange(T, device=x.device))
        return self.head(self.ln(self.blocks(h)))      # (batch, T, vocab)
""")

md("""
## 6. Generation: predict, sample, append, repeat

The model gives logits for the next character. Divide by the temperature, softmax, sample one,
append it, and repeat.
""")
code("""
@torch.no_grad()
def generate(prompt, n=200, temperature=1.0):
    ids = torch.tensor([encode(prompt)], device=device)
    for _ in range(n):
        logits = model(ids[:, -block_size:])[:, -1, :]    # next-token logits
        p = F.softmax(logits / temperature, dim=-1)       # probabilities
        nxt = torch.multinomial(p, num_samples=1)         # sample one
        ids = torch.cat([ids, nxt], dim=1)                # append, repeat
    return decode(ids[0].tolist())


@torch.no_grad()
def val_loss(n_batches=20):
    model.eval()
    total = 0.0
    for _ in range(n_batches):
        x, y = get_batch("val")
        logits = model(x)
        total += F.cross_entropy(logits.view(-1, vocab_size),
                                 y.view(-1)).item()
    model.train()
    return total / n_batches
""")

md("""
## 7. Training: next-token loss at every position

Each step takes 64 windows of 128 characters: 8,192 next-character predictions, averaged into
one cross-entropy loss. Every 250 steps we check the loss on held-out text and sample from the
model.
""")
code("""
torch.manual_seed(0)
model = TinyGPT().to(device)
optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
print(sum(p.numel() for p in model.parameters()), "parameters")

steps = 2000          # on a CPU, try 500 first
losses = []           # training loss at every step
history = []          # (step, validation loss, sample) every 250 steps
start = time.time()
for step in range(steps + 1):
    x, y = get_batch("train")
    logits = model(x)                                   # (batch, T, vocab)
    loss = F.cross_entropy(logits.view(-1, vocab_size), y.view(-1))
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    losses.append(loss.item())
    if step % 250 == 0:
        sample = generate("The model ", n=120, temperature=0.8)
        history.append((step, val_loss(), sample))
        print(f"step {step:4d}  train {loss.item():.2f}  "
              f"val {history[-1][1]:.2f}  ({time.time() - start:.0f} s)")
""")

md("""
## 8. What it learned, step by step
""")
code("""
fig, ax = plt.subplots(figsize=(7, 3.5))
ax.plot(losses, alpha=0.5, label="training (each step)")
ax.plot([h[0] for h in history], [h[1] for h in history], "o-",
        label="held-out text")
ax.set_xlabel("training step")
ax.set_ylabel("next-character loss")
ax.legend()
plt.show()

for step, vl, sample in history[::2]:
    print(f"--- step {step}, held-out loss {vl:.2f}")
    print(sample, "\\n")
""")

md("""
## 9. Temperature

Low temperature: the most likely characters, repetitive. High temperature: more surprising,
and more mistakes.
""")
code("""
torch.manual_seed(1)
for t in (0.3, 0.8, 1.5):
    print(f"--- temperature {t}")
    print(generate("A Gaussian process ", n=200, temperature=t), "\\n")
""")

md("""
## 10. What it learned: our vocabulary

A fair test of what the model knows. Take one key term from each of Lectures 1 to 16, give the
model the first 60% of its characters, and let it pick the most likely next character until the
term should end. No sampling, so the answer is the same every time.
""")
code("""
@torch.no_grad()
def complete(prompt, n):
    # the most likely next character, n times: no sampling
    ids = torch.tensor([encode(prompt)], device=device)
    for _ in range(n):
        nxt = model(ids[:, -block_size:])[:, -1, :].argmax(-1, keepdim=True)
        ids = torch.cat([ids, nxt], dim=1)
    return decode(ids[0].tolist())[len(prompt):]


terms = ["toolchain", "environment", "database", "Parquet", "dataframe", "validation",
         "steady state", "forecast", "regression", "classification", "gradient",
         "convolution", "physics-informed", "uncertainty", "Bayesian optimization",
         "distribution"]                       # one term from each of Lectures 1 to 16
results = []
for lecture, term in enumerate(terms, 1):
    k = -(-6 * len(term) // 10)                # the first 60% of the characters
    guess = complete(" " + term[:k], len(term) - k)
    results.append((term, term[:k], guess))
    print(f"L{lecture:<3}{term[:k]:>14} + {guess!r:12} {'right' if guess == term[k:] else 'wrong'}")
right = sum(g == t[len(p):] for t, p, g in results)
print(f"{right} of {len(terms)} terms finished correctly")
""")

md("""
It spells our vocabulary. It does not write sentences with meaning: the samples above are fluent
nonsense. Meaning takes far more parameters and far more text, which is the scale part of the
lecture.
""")

md("""
## Try it

- Change the prompt: `"Bayesian optimization "`, `"The data "`, `"def "`. What has it learned about
  each?
- Set the temperature to 0.01. Why does the text start to repeat?
- Double `n_embd` to 256. How many parameters now, how long does training take, and how low does
  the held-out loss go?
- Train for 6,000 steps. Watch the training and held-out losses: when do they separate, and
  what does that mean?
""")


def notebook(cells):
    return {"cells": cells, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}


if __name__ == "__main__":
    sys.path.insert(0, str(HERE.parent.parent / "tools"))
    from colab_setup import with_colab_cell
    OUT.write_text(json.dumps(notebook(with_colab_cell(list(CELLS), OUT)), indent=1) + "\n")
    print(f"wrote {OUT.name} ({len(CELLS)} cells)")
