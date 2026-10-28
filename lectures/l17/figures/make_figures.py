#!/usr/bin/env python3
"""Generate the L17 figures and the data behind its interactive figures, and print every number
the notes and the deck quote.

Run from this directory:
    uv run --no-project --python 3.12 --with torch --with matplotlib --with nbclient \
        --with nbformat --with ipykernel --with tiktoken --with transformers --with scipy \
        --with scikit-learn --with polars --with pyarrow --with pyreadr --with pandas python make_figures.py

Name groups to regenerate only those; with no names, every group runs.

    tiny     executes ../worked-example/l17-tiny-llm.ipynb once (the cells come from
             ../worked-example/build_notebook.py),
             writes it back with its outputs, and builds tiny-loss.png and the "train" widget
             data from that same run. About three minutes on an Apple-silicon GPU.
    tinyfig  redraws tiny-loss.png and the "train" and "learn" widget data from the cached
             run, without training again.
    bpe      byte-pair encoding, trained on the same corpus, applied merge by merge to one
             engineering sentence: the "bpe" widget data, and bpe.png.
    tokens   tokens.png: how GPT-4o's tokenizer (tiktoken, o200k_base) splits engineering text.
    gpt2     next-token probabilities from GPT-2 (124M) along a greedy continuation: the
             "sample" widget data, and temperature.png.
    scale    scale.png: parameters against training tokens, our tiny model next to GPT-3,
             Chinchilla and Llama 3.
    examples the small worked examples: the chain rule on "The pump stopped" (GPT-2), token ids,
             one sentence cut three ways, byte-pair encoding on a toy corpus, and the window the
             causal-mask animation steps through. Needs the gpt2 group's cache.
    sizes    the data behind the models-over-the-years animation: release dates and parameter
             counts from each model's source, and the closed models, whose sizes are not published.
    concepts look-back.png, attention looking back (illustrative weights), and neglog.png, the
             loss -ln p of one prediction.
    chat     a small open chat model (Qwen2.5-0.5B-Instruct, downloaded once, about 1 GB) answering
             two questions greedily: the hidden script, and its top-5 next tokens at every step.
    twoways  two-ways.png: Lecture 16's |x| data and Gaussian mixture, sampled at once and one
             variable at a time.
    ar       ar-recursive.png: Lecture 8's AR(10) on reactor pressure, forecast recursively. Uses
             Lecture 8's loader, which downloads the Tennessee Eastman data (25 MB) once.
    optmap   decision-map.png: Lecture 15's sketch of where each optimizer fits, with the tiny GPT.
    window   window.png: one context window is T next-token predictions, and the causal mask;
             mask-pump.png: the causal mask on the words of the pump sentence.

Results are cached under .cache/ (gitignored).
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
LECTURE = HERE.parent
REPO = HERE.parents[2]
CACHE = HERE / ".cache"
CACHE.mkdir(exist_ok=True)
WIDGET_JS = REPO / "_static" / "l17-widget-data.js"

RED, BLUE, GOLD, GREEN, GRAY = "#c41230", "#1f5c99", "#b07d12", "#2e7d32", "#8a8a8a"
PALETTE = ["#dbe8f5", "#f7e3c3", "#dcefdc", "#f6d9de", "#e8e0f2", "#d9f0ee"]
plt.rcParams.update({"font.size": 13, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.dpi": 150, "savefig.bbox": "tight"})


def save(fig, name):
    fig.savefig(HERE / name)
    plt.close(fig)
    print(f"  wrote {name}")


def cache_put(name, obj):
    (CACHE / f"{name}.json").write_text(json.dumps(obj))


def cache_get(name):
    return json.loads((CACHE / f"{name}.json").read_text())


# ------------------------------------------------------------------------ tiny
PROBE_SENTENCE = "A generative model learns the probability distribution of the data."


def group_tiny():
    import nbformat
    from nbclient import NotebookClient
    sys.path.insert(0, str(LECTURE / "worked-example"))
    sys.path.insert(0, str(REPO / "tools"))
    import build_notebook as bn
    from colab_setup import with_colab_cell

    dump = ("import json\n"
            "json.dump({'losses': losses, 'history': history, 'vocab_size': vocab_size,\n"
            "           'chars': len(text), 'train_chars': len(train_data),\n"
            "           'params': sum(p.numel() for p in model.parameters()),\n"
            "           'block_size': block_size, 'batch_size': batch_size, 'steps': steps,\n"
            "           'device': device, 'seconds': time.time() - start,\n"
            "           'probe': PROBE, 'probe_log': probe_log[:len(history)],\n"
            "           'terms': results, 'terms_right': right},\n"
            "          open('figures/.cache/tiny.json', 'w'))\n"
            "open('figures/.cache/corpus.txt', 'w').write(text)\n")
    # a probe, run inside every call to generate() during training (every 250 steps): the
    # probability the model gives each true next character of one held-out sentence. It uses
    # no random numbers, so the notebook's own outputs are the same with or without it.
    probe = ("PROBE = " + repr(PROBE_SENTENCE) + "\n"
             "probe_log = []\n"
             "_generate = generate\n\n\n"
             "def generate(prompt, n=200, temperature=1.0):\n"
             "    with torch.no_grad():\n"
             "        ids = torch.tensor([encode(PROBE)], device=device)\n"
             "        p = F.softmax(model(ids[:, :-1]), dim=-1)[0]\n"
             "        tgt = ids[0, 1:]\n"
             "        t5 = torch.topk(p, 5)\n"
             "        probe_log.append({'p': p[torch.arange(len(tgt)), tgt].tolist(),\n"
             "                          'top': [itos[i] for i in p.argmax(-1).tolist()],\n"
             "                          'top5': [[[itos[i], round(v, 4)] for v, i in zip(vs, ix)]\n"
             "                                   for vs, ix in zip(t5.values.tolist(), t5.indices.tolist())]})\n"
             "    return _generate(prompt, n, temperature)\n")
    cells = [dict(c) for c in bn.CELLS]
    at = next(k for k, c in enumerate(cells) if c["id"] == "code-13") + 1
    cells.insert(at, {"cell_type": "code", "id": "probe", "execution_count": None, "metadata": {},
                      "outputs": [], "source": probe})
    cells.append({"cell_type": "code", "id": "dump", "execution_count": None, "metadata": {},
                  "outputs": [], "source": dump})
    nb = nbformat.reads(json.dumps(bn.notebook(cells)), as_version=4)
    NotebookClient(nb, timeout=3600, resources={"metadata": {"path": str(LECTURE)}}).execute()
    done = json.loads(nbformat.writes(nb))
    done["cells"] = [c for c in done["cells"] if c.get("id") not in ("probe", "dump")]
    done["cells"] = with_colab_cell(done["cells"], bn.OUT)
    bn.OUT.write_text(json.dumps(done, indent=1) + "\n")
    print(f"  executed and wrote {bn.OUT.name}")

    draw_tiny()


# what the samples of the training run show, one line per evaluation (every 250 steps); they
# describe the samples printed by draw_tiny, so rewrite them if a retrain changes those
TRAIN_NOTES = [
    "random characters. It gives every character about the same chance.",
    "letters, spaces and line breaks, but almost no real words.",
    "short real words (is, you, and, with), glued into nonsense.",
    "longer words from our notes (model, works), still no sentences.",
    "mostly real words, with the rhythm of a sentence.",
    "real phrases from the course: residual, forecaster, Markdown headings.",
    "the course's vocabulary: time-series, a citation in square brackets.",
    "close to its best held-out loss. Fluent nonsense, in our style.",
    "LaTeX copied from our notes (\\frac{dX}{dt}): it learned the style, not the meaning.",
]


def draw_tiny():
    t = cache_get("tiny")
    hist = t["history"]
    seen = (t["steps"] + 1) * t["batch_size"] * t["block_size"]
    print(f"  corpus {t['chars']:,} characters ({t['train_chars']:,} to train), vocabulary "
          f"{t['vocab_size']}, {t['params']:,} parameters, device {t['device']}, "
          f"{t['seconds']:.0f} s")
    print(f"  tokens seen in training: {seen:,} = {seen / t['params']:.1f} per parameter")
    for step, vl, sample in hist:
        print(f"  step {step:4d}: held-out loss {vl:.3f} | {sample[:70]!r}")

    losses = np.array(t["losses"])
    fig, ax = plt.subplots(figsize=(8.0, 3.8))
    ax.plot(losses, color=BLUE, alpha=0.35, lw=1, label="training batch, each step")
    ax.plot([h[0] for h in hist], [h[1] for h in hist], "o-", color=RED, lw=2,
            label="held-out text (last 10%)")
    v = t["vocab_size"]
    ax.axhline(np.log(v), color=GRAY, ls=":", lw=1.5)
    ax.text(t["steps"], np.log(v) + 0.1, f"knows nothing: 1/{v} for every character, "
            f"loss {np.log(v):.2f}", ha="right", fontsize=10.5, color=GRAY)
    fin = hist[-1][1]
    ax.annotate(f"{fin:.2f}: the right character typically\ngets $e^{{-{fin:.2f}}}$ = {np.exp(-fin):.0%}",
                (hist[-1][0], fin), xytext=(-14, 34), textcoords="offset points", ha="right",
                color=RED, fontsize=11, arrowprops=dict(arrowstyle="->", color=RED, lw=1))
    ax.set_xlabel("training step")
    ax.set_ylabel("next-character loss")
    ax.set_ylim(0, 5.5)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=11, frameon=False)
    save(fig, "tiny-loss.png")

    learn = []
    for (step, vl, _), pl in zip(hist, t["probe_log"]):
        loss = float(-np.mean(np.log(np.maximum(pl["p"], 1e-12))))
        learn.append({"step": step, "p": [round(v, 3) for v in pl["p"]], "top": pl["top"], "loss": round(loss, 3),
                      "top5": pl.get("top5")})
        print(f"  probe at step {step}: loss {loss:.2f}, top guesses {''.join(pl['top'])[:50]!r}")
    # the position the training animation opens on: the "b" after "the proba", which the model
    # gives almost nothing at step 500 and almost everything at the end
    focus = t["probe"].index("learns the proba") + len("learns the proba") - 1
    print(f"  dials focus: after {t['probe'][:focus + 1]!r}, p(true) by step: "
          f"{[round(f['p'][focus], 2) for f in learn]}")
    cache_put("learn", {"sentence": t["probe"], "frames": learn, "focus": focus,
                        "uniform": round(float(np.log(t["vocab_size"])), 3)})
    if t.get("terms"):
        cache_put("terms", {"terms": t["terms"], "right": t["terms_right"]})
        print(f"  terms finished correctly: {t['terms_right']} of {len(t['terms'])}")
    cache_put("train", {"steps": [h[0] for h in hist], "val": [round(h[1], 3) for h in hist],
                        "samples": [h[2] for h in hist],
                        "loss": [round(float(v), 3) for v in losses[::10]], "every": 10,
                        "uniform": round(float(np.log(t["vocab_size"])), 3),
                        "params": t["params"], "vocab": t["vocab_size"], "notes": TRAIN_NOTES})


# ------------------------------------------------------------------------ bpe
PRETOKEN = re.compile(r" ?[A-Za-z]+| ?[0-9]+| ?[^\sA-Za-z0-9]+|\s+")
PHRASE = "The pump temperature rose to 85 °C."
N_MERGES = 600


def bpe_train(text, n_merges):
    # Sennrich et al. (2016): count adjacent symbol pairs, merge the most frequent, repeat
    words = Counter(tuple(w) for w in PRETOKEN.findall(text))
    merges = []
    for _ in range(n_merges):
        pairs = Counter()
        for w, f in words.items():
            for a, b in zip(w, w[1:]):
                pairs[a, b] += f
        if not pairs:
            break
        (a, b), count = pairs.most_common(1)[0]
        merges.append((a, b, count))
        new = Counter()
        for w, f in words.items():
            out, i = [], 0
            while i < len(w):
                if i < len(w) - 1 and w[i] == a and w[i + 1] == b:
                    out.append(a + b)
                    i += 2
                else:
                    out.append(w[i])
                    i += 1
            new[tuple(out)] += f
        words = new
    return merges


def bpe_frames(phrase, merges):
    # apply the merges in the order they were learned; keep the ones that change the phrase
    words = [list(w) for w in PRETOKEN.findall(phrase)]
    flat = lambda: [t for w in words for t in w]
    frames = [{"merge": None, "rank": 0, "tokens": flat()}]
    for rank, (a, b, count) in enumerate(merges, 1):
        changed = False
        for w in words:
            i = 0
            while i < len(w) - 1:
                if w[i] == a and w[i + 1] == b:
                    w[i:i + 2] = [a + b]
                    changed = True
                else:
                    i += 1
        if changed:
            frames.append({"merge": [a, b], "rank": rank, "count": count, "tokens": flat()})
    return frames


def group_bpe():
    import tiktoken
    text = (CACHE / "corpus.txt").read_text()
    merges = bpe_train(text, N_MERGES)
    print(f"  {len(merges)} merges; the first ten: {[a + b for a, b, _ in merges[:10]]}")
    frames = bpe_frames(PHRASE, merges)
    enc = tiktoken.get_encoding("o200k_base")
    gpt4o = [enc.decode([i]) for i in enc.encode(PHRASE)]
    print(f"  {PHRASE!r}: {len(frames[0]['tokens'])} characters -> {len(frames[-1]['tokens'])} tokens "
          f"after {len(frames) - 1} of the merges; GPT-4o's tokenizer: {len(gpt4o)} tokens")
    for f in frames[1:6]:
        print(f"    merge {f['rank']}: {f['merge'][0]!r} + {f['merge'][1]!r}, seen {f['count']:,} times")
    cache_put("bpe", {"phrase": PHRASE, "frames": frames, "gpt4o": gpt4o, "n_merges": len(merges),
                      "corpus_chars": len(text)})

    # the phrase before, part-way and after, as a picture for the notes
    picks = [0, len(frames) // 3, len(frames) - 1]
    fig, ax = plt.subplots(figsize=(10.0, 3.6))
    ax.axis("off")
    rows = [(f"start: {len(frames[k]['tokens'])} characters" if k == 0 else
             f"after merge {frames[k]['rank']}: {len(frames[k]['tokens'])} tokens", frames[k]["tokens"])
            for k in picks] + [(f"GPT-4o's tokenizer: {len(gpt4o)} tokens", gpt4o)]
    draw_token_rows(ax, rows)
    save(fig, "bpe.png")


def text_width(ax, s, fontsize, family=None):
    # width of a string in axes units, measured with the renderer
    t = ax.text(0, 0, s, fontsize=fontsize, family=family, transform=ax.transAxes)
    ax.figure.canvas.draw()
    w = t.get_window_extent().width / ax.get_window_extent().width
    t.remove()
    return w


def draw_token_rows(ax, rows, fontsize=11):
    # each token as a colored box, monospace, one row per tokenization; the font shrinks
    # until the longest row fits inside the axes
    mono = "DejaVu Sans Mono"
    while True:
        cw = text_width(ax, "M" * 40, fontsize, mono) / 40
        pad = cw * 0.35
        label_w = max(text_width(ax, label, fontsize) for label, _ in rows) + 0.02
        need = max(label_w + sum(cw * len(t) + 2 * pad + cw * 0.25 for t in toks) for _, toks in rows)
        if need <= 1 or fontsize <= 7:
            break
        fontsize -= 0.5
    for r, (label, toks) in enumerate(rows):
        y = 1 - (r + 0.6) / len(rows)
        ax.text(0, y, label, fontsize=fontsize, va="center", color=GRAY, transform=ax.transAxes)
        x = label_w
        for j, t in enumerate(toks):
            shown = t.replace(" ", "\u2423")
            w = cw * len(shown) + 2 * pad
            ax.add_patch(plt.Rectangle((x, y - 0.11), w, 0.22, transform=ax.transAxes, clip_on=False,
                                       fc=PALETTE[j % len(PALETTE)], ec="white", lw=1.5))
            ax.text(x + w / 2, y, shown, transform=ax.transAxes, ha="center", va="center",
                    fontsize=fontsize, family=mono)
            x += w + cw * 0.25


# ------------------------------------------------------------------------ tokens
STRINGS = ["heat exchanger", "±0.05 mm AISI 4140 bearing", "Pump P-101A trips at 12.5 bar",
           "Q = 1.5e-3 m³/s", "CH3CH2OH"]


def group_tokens():
    import tiktoken
    enc = tiktoken.get_encoding("o200k_base")
    rows = []
    for s in STRINGS:
        toks = [enc.decode([i]) for i in enc.encode(s)]
        rows.append((f"{len(s)} characters, {len(toks)} tokens", toks))
        print(f"  {s!r}: {len(s)} characters, {len(toks)} tokens: {toks}")
    fig, ax = plt.subplots(figsize=(11.0, 3.8))
    ax.axis("off")
    draw_token_rows(ax, rows, fontsize=12)
    save(fig, "tokens.png")


# ------------------------------------------------------------------------ gpt2
PROMPT = "The pump stopped because the"
HALLUCINATE = "The reactor temperature rose to"
TOP = 20
TEMPS = [round(0.1 * k, 1) for k in range(1, 21)]      # 0.1 to 2.0


def group_gpt2():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(1)
    tok = AutoTokenizer.from_pretrained("gpt2")
    model = AutoModelForCausalLM.from_pretrained("gpt2").eval()

    def greedy(prompt, n):
        ids = tok(prompt, return_tensors="pt").input_ids
        steps = []
        for _ in range(n):
            with torch.no_grad():
                logits = model(ids).logits[0, -1]
            top = torch.topk(logits, TOP)
            p = torch.softmax(logits, -1)
            # log of the softmax denominator over the whole vocabulary, at each temperature, so the
            # widget can show exact probabilities for the top tokens at any temperature on the grid
            lse = [round(float(torch.logsumexp(logits / t, 0)), 4) for t in TEMPS]
            steps.append({"context": tok.decode(ids[0]), "tokens": [tok.decode([i]) for i in top.indices],
                          "logits": [round(float(v), 4) for v in top.values], "lse": lse,
                          "p": [round(float(p[i]), 4) for i in top.indices],
                          "top_mass": round(float(p[top.indices].sum()), 3)})
            ids = torch.cat([ids, top.indices[:1].view(1, 1)], 1)
        return steps, tok.decode(ids[0])

    steps, full = greedy(PROMPT, 5)
    print(f"  {PROMPT!r} -> greedy: {full[len(PROMPT):]!r}")
    for s in steps[:4]:
        print(f"    top 5: {list(zip(s['tokens'][:5], s['p'][:5]))}, top {TOP} hold {s['top_mass']:.0%}")
    _, hall = greedy(HALLUCINATE, 7)
    print(f"  {HALLUCINATE!r} -> greedy: {hall[len(HALLUCINATE):]!r}")
    cache_put("sample", {"prompt": PROMPT, "steps": steps, "top": TOP, "temps": TEMPS, "model": "GPT-2 (124M)"})

    # one step at three temperatures, over the whole vocabulary: the step where GPT-2 is confident
    context = steps[3]["context"]
    ids = tok(context, return_tensors="pt").input_ids
    with torch.no_grad():
        logits = model(ids).logits[0, -1]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True)
    order = torch.topk(logits, 8).indices
    for ax, temp in zip(axes, (0.5, 1.0, 2.0)):
        p = torch.softmax(logits / temp, -1)
        vals = [float(p[i]) for i in order]
        ax.bar(range(8), vals, color=[RED if k == 0 else BLUE for k in range(8)])
        ax.set_xticks(range(8))
        ax.set_xticklabels([tok.decode([i]).strip() for i in order], rotation=45, ha="right", fontsize=11)
        ax.set_title(f"temperature {temp:g}: top 8 hold {sum(vals):.0%}", fontsize=12)
        print(f"  temperature {temp:g}: top token {vals[0]:.3f}, top 8 hold {sum(vals):.2f}")
    axes[0].set_ylabel("probability")
    fig.suptitle(f"GPT-2, next token after \"{context}\"", fontsize=13, y=1.03)
    save(fig, "temperature.png")


# ------------------------------------------------------------------------ examples
TOY = ["pump"] * 5 + ["pumps"] * 2 + ["pumping"] * 2 + ["dump"] * 3


def group_examples():
    # the small worked examples the deck and notes quote: GPT-2 on "The pump stopped", the tokens
    # of one sentence three ways, and byte-pair encoding on a toy corpus
    import tiktoken
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(1)
    tok = AutoTokenizer.from_pretrained("gpt2")
    model = AutoModelForCausalLM.from_pretrained("gpt2").eval()
    out = {}

    # the chain rule on a real sentence: p(The) p( pump | The) p( stopped | The pump)
    ids = [tok.eos_token_id] + tok("The pump stopped").input_ids
    with torch.no_grad():
        logp = torch.log_softmax(model(torch.tensor([ids])).logits[0], -1)
    chain = []
    for t in range(1, len(ids)):
        lp = float(logp[t - 1, ids[t]])
        chain.append({"token": tok.decode([ids[t]]), "p": float(np.exp(lp)), "logp": lp})
    total = sum(c["logp"] for c in chain)
    out["chain"] = {"tokens": chain, "p_text": float(np.exp(total)), "logp_text": total}
    for c in chain:
        print(f"  p({c['token']!r} | before) = {c['p']:.4f}, log p = {c['logp']:.2f}")
    print(f"  p('The pump stopped') = {np.exp(total):.2e} (log {total:.2f})")

    # tokens and ids, GPT-2's tokenizer (tiktoken's "gpt2" encoding, the same vocabulary as r50k_base)
    enc = tiktoken.get_encoding("gpt2")
    sent = "The pump stopped."
    tids = enc.encode(sent)
    out["ids"] = {"text": sent, "tokens": [enc.decode([i]) for i in tids], "ids": tids, "vocab": enc.n_vocab}
    # a few rows of the vocabulary itself: its first entries, the four tokens above, and its last
    rows = sorted(set([0, 1, 2] + tids + [enc.n_vocab - 1]))
    out["vocab_rows"] = [[i, enc.decode([i])] for i in rows]
    print(f"  GPT-2 vocabulary rows: {out['vocab_rows']}")
    print(f"  GPT-2 tokens of {sent!r}: {out['ids']['tokens']} ids {tids}; vocabulary {enc.n_vocab:,}")

    # the window the causal-mask animation steps through
    s3 = "The pump stopped because the water was too hot."
    out["causal"] = [enc.decode([i]) for i in enc.encode(s3)]
    print(f"  causal window: {out['causal']}")

    # the big-picture animation: GPT-2's tokens of one sentence, and its real next-token probabilities
    s4 = "The plant shut down for maintenance"
    ids4 = tok(s4, return_tensors="pt").input_ids
    with torch.no_grad():
        p4 = torch.softmax(model(ids4).logits[0, -1], -1)
    t4 = torch.topk(p4, 6)
    out["flow"] = {"text": s4, "tokens": [tok.decode([int(i)]) for i in ids4[0]],
                   "next": [[tok.decode([int(i)]), round(float(v), 4)] for v, i in zip(t4.values, t4.indices)]}
    print(f"  flow: {out['flow']['tokens']} -> {out['flow']['next']}")

    # how many tokens our notes are, against a context window
    corpus = (CACHE / "corpus.txt").read_text()
    out["notes_tokens"] = len(tiktoken.get_encoding("o200k_base").encode(corpus))
    # words per GPT-2 token in our notes, to put GPT-3's 300 billion training tokens into reading time
    out["notes_words"] = len(corpus.split())
    out["notes_tokens_gpt2"] = len(enc.encode(corpus))
    years = 300e9 * out["notes_words"] / out["notes_tokens_gpt2"] / 250 / 60 / 24 / 365.25
    print(f"  our notes: {out['notes_words']:,} words, {out['notes_tokens_gpt2']:,} GPT-2 tokens "
          f"({out['notes_words'] / out['notes_tokens_gpt2']:.2f} words per token); GPT-3's 300 billion "
          f"tokens at that rate and 250 words a minute: {years:,.0f} years")
    print(f"  our notes: {len(corpus):,} characters, {out['notes_tokens']:,} GPT-4o tokens "
          f"({len(corpus) / out['notes_tokens']:.2f} characters per token)")

    # one sentence, cut three ways
    s2 = "The pump overheated at 85 °C."      # common words whole, "overheated" in two pieces
    g2 = [enc.decode([i]) for i in enc.encode(s2)]
    out["three"] = {"text": s2, "chars": list(s2), "words": s2.split(" "), "gpt2": g2}
    print(f"  {s2!r}: {len(s2)} characters, {len(s2.split(' '))} words, {len(g2)} GPT-2 tokens {g2}")

    # byte-pair encoding on a toy corpus: the pair counts before each merge
    words = Counter(tuple(w) for w in TOY)
    steps = []
    for _ in range(4):
        pairs = Counter()
        for w, f in words.items():
            for a, b in zip(w, w[1:]):
                pairs[a, b] += f
        (a, b), n = pairs.most_common(1)[0]
        steps.append({"pairs": [[x + "+" + y, c] for (x, y), c in pairs.most_common(5)], "merge": [a, b], "count": n,
                      "words": {"".join(w): " ".join(w) for w in words}})
        new = Counter()
        for w, f in words.items():
            o, i = [], 0
            while i < len(w):
                if i < len(w) - 1 and w[i] == a and w[i + 1] == b:
                    o.append(a + b)
                    i += 2
                else:
                    o.append(w[i])
                    i += 1
            new[tuple(o)] += f
        words = new
    steps.append({"words": {"".join(w): " ".join(w) for w in words}})
    out["toy"] = {"corpus": dict(Counter(TOY)), "steps": steps}
    for k, st in enumerate(steps[:-1], 1):
        print(f"  toy merge {k}: {st['merge'][0]!r} + {st['merge'][1]!r} (count {st['count']}); "
              f"top pairs {st['pairs'][:3]}")
    print(f"  after 4 merges: {steps[-1]['words']}")

    # a pretrained model continues text rather than answering it, and states a false number fluently
    def greedy(prompt, n):
        ids = tok(prompt, return_tensors="pt").input_ids
        for _ in range(n):
            with torch.no_grad():
                nxt = model(ids).logits[0, -1].argmax().view(1, 1)
            ids = torch.cat([ids, nxt], 1)
        return tok.decode(ids[0])[len(prompt):]

    q1 = "What is the boiling point of water?"
    q2 = "Question: What is the boiling point of water at sea level?\nAnswer:"
    out["continue"] = {"prompt": q1, "text": greedy(q1, 30).strip()}
    out["qa"] = {"prompt": q2, "text": greedy(q2, 20).split("\n")[0].strip()}
    print(f"  GPT-2 after {q1!r}: {out['continue']['text']!r}")
    print(f"  GPT-2 after {q2!r}: {out['qa']['text']!r}")

    # logits and probabilities for the first step of the pump sentence
    smp = cache_get("sample")["steps"][0]
    print(f"  logits at step 1: {list(zip(smp['tokens'][:3], smp['logits'][:3]))}; p {smp['p'][:3]}")
    j = 0                                                       # temperature 0.1
    print(f"  p(water) at temperature 0.1: {np.exp(smp['logits'][0] / 0.1 - smp['lse'][j]):.3f}")
    cache_put("examples", out)


# ------------------------------------------------------------------------ scale
MODELS = [  # name, parameters, training tokens, source
    ("GPT-3", 175e9, 300e9, "Brown et al. 2020"),
    ("Chinchilla", 70e9, 1.4e12, "Hoffmann et al. 2022"),
    ("Llama 3 405B", 405e9, 15.6e12, "Llama Team 2024"),
]


def group_scale():
    t = cache_get("tiny")
    seen = (t["steps"] + 1) * t["batch_size"] * t["block_size"]
    rows = MODELS + [("our tiny GPT", float(t["params"]), float(seen), "this notebook")]
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    n = np.logspace(5, 12.5, 50)
    ax.plot(n, 20 * n, color=GREEN, ls="--", lw=1.5)
    ax.text(2e7, 20 * 2e7 * 3.0, "20 tokens per parameter", color=GREEN, fontsize=11, rotation=27)
    offsets = {"GPT-3": (12, -4, "left", "top"), "Chinchilla": (-12, 4, "right", "bottom"),
               "Llama 3 405B": (-12, 6, "right", "bottom"), "our tiny GPT": (14, -2, "left", "top")}
    for name, p, d, _ in rows:
        ours = name.startswith("our")
        ax.plot(p, d, "*" if ours else "o", ms=16 if ours else 10, color=RED if ours else BLUE, mec="k")
        dx, dy, ha, va = offsets[name]
        ax.annotate(f"{name}\n{d / p:.1f} tokens per parameter", (p, d), xytext=(dx, dy),
                    textcoords="offset points", fontsize=10.5, ha=ha, va=va,
                    bbox=dict(fc="white", ec="none", alpha=0.85, pad=1))
        print(f"  {name}: {p:.3g} parameters, {d:.3g} tokens, {d / p:.1f} tokens per parameter")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(1e5, 3e13)
    ax.set_ylim(3e6, 1e15)
    ax.set_xlabel("parameters")
    ax.set_ylabel("training tokens")
    save(fig, "scale.png")


# ------------------------------------------------------------------------ window
def group_window():
    word = "Gaussian"
    T = len(word) - 1
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 3.8), gridspec_kw={"width_ratios": [1.35, 1]})
    ax = axes[0]
    ax.axis("off")
    ax.set_xlim(-1.2, T + 0.2)
    ax.set_ylim(-0.6, 2.6)
    for t in range(T):
        for row, ch, col in ((2, word[t], PALETTE[0]), (0, word[t + 1], PALETTE[2])):
            ax.add_patch(plt.Rectangle((t, row), 0.86, 0.72, fc=col, ec="white"))
            ax.text(t + 0.43, row + 0.36, ch, ha="center", va="center", fontsize=15, family="DejaVu Sans Mono")
        ax.annotate("", (t + 0.43, 0.78), (t + 0.43, 1.95), arrowprops=dict(arrowstyle="->", color=GRAY))
    ax.text(-0.15, 2.36, "input", ha="right", va="center", fontsize=12, color=BLUE)
    ax.text(-0.15, 0.36, "target", ha="right", va="center", fontsize=12, color=GREEN)
    ax.text(T / 2, -0.45, f"one window of {T} tokens = {T} next-token predictions", ha="center", fontsize=12)
    ax = axes[1]
    mask = np.tril(np.ones((T, T)))
    ax.imshow(mask, cmap=matplotlib.colors.ListedColormap(["#f2f2f2", "#9cc3e6"]), vmin=0, vmax=1)
    ax.set_xticks(range(T))
    ax.set_xticklabels(list(word[:T]), family="DejaVu Sans Mono")
    ax.set_yticks(range(T))
    ax.set_yticklabels([f"predicts '{word[t + 1]}'" for t in range(T)], fontsize=10)
    ax.xaxis.tick_top()
    ax.set_title("causal mask: who each position sees", fontsize=12, pad=26)
    for s in ax.spines.values():
        s.set_visible(False)
    save(fig, "window.png")

    # the causal mask on words, for the attention slide: row "stopped" may look at "The pump
    # stopped", and the mask hides "because the" (GPT-2's tokens of the prompt)
    toks = ["The", "␣pump", "␣stopped", "␣because", "␣the"]
    n = len(toks)
    fig, ax = plt.subplots(figsize=(5.6, 4.4))
    for i in range(n):
        for j in range(n):
            seen = j <= i
            fc = "#9cc3e6" if seen else "#efefef"
            if i == 2:
                fc = "#5b9bd5" if seen else "#e2e2e2"
            ax.add_patch(plt.Rectangle((j, i), 0.94, 0.94, fc=fc, ec="white"))
            ax.text(j + 0.47, i + 0.47, "" if seen else "−∞", ha="center", va="center",
                    fontsize=13, color="#7a7a7a")
    ax.add_patch(plt.Rectangle((-0.04, 1.97), n + 0.02, 1.0, fill=False, ec=RED, lw=2.2))
    ax.set_xlim(-0.1, n)
    ax.set_ylim(n, -0.1)
    ax.set_xticks([j + 0.47 for j in range(n)])
    ax.set_xticklabels(toks, family="DejaVu Sans Mono", fontsize=11, rotation=30, ha="left")
    ax.set_yticks([i + 0.47 for i in range(n)])
    ax.set_yticklabels(toks, family="DejaVu Sans Mono", fontsize=11)
    ax.xaxis.tick_top()
    ax.tick_params(length=0)
    ax.set_xlabel("looks at", fontsize=12, labelpad=8)
    ax.xaxis.set_label_position("top")
    ax.set_ylabel("token", fontsize=12)
    for sp in ax.spines.values():
        sp.set_visible(False)
    save(fig, "mask-pump.png")


# ------------------------------------------------------------------------ sizes
# Language models by release date and parameter count, from each model's own paper, model card or
# announcement (checked 2026-10-28). Mixture-of-experts models also give the parameters active for
# each token. Closed models publish no size; they are drawn on a strip at their release date.
SIZES_OPEN = [  # name, year as a decimal, total parameters, active parameters or None, source
    ("GPT-1", 2018.44, 117e6, None, "https://cdn.openai.com/better-language-models/language_models_are_unsupervised_multitask_learners.pdf"),
    ("GPT-2", 2019.12, 1.5e9, None, "https://cdn.openai.com/better-language-models/language_models_are_unsupervised_multitask_learners.pdf"),
    ("GPT-3", 2020.41, 175e9, None, "https://arxiv.org/abs/2005.14165"),
    ("Gopher", 2021.94, 280e9, None, "https://arxiv.org/abs/2112.11446"),
    ("Chinchilla", 2022.24, 70e9, None, "https://arxiv.org/abs/2203.15556"),
    ("PaLM", 2022.26, 540e9, None, "https://arxiv.org/abs/2204.02311"),
    ("Llama 2", 2023.55, 70e9, None, "https://arxiv.org/abs/2307.09288"),
    ("Llama 3.1", 2024.56, 405e9, None, "https://arxiv.org/abs/2407.21783"),
    ("DeepSeek-V3", 2024.99, 671e9, 37e9, "https://arxiv.org/abs/2412.19437"),
    ("Kimi K2", 2025.53, 1.0e12, 32e9, "https://arxiv.org/abs/2507.20534"),
    ("DeepSeek-V4-Pro", 2026.31, 1.6e12, 49e9, "https://api-docs.deepseek.com/news/news260424"),
    ("Kimi K3", 2026.54, 2.8e12, 104e9, "https://huggingface.co/moonshotai/Kimi-K3"),
]
SIZES_CLOSED = [  # name, year, source; sizes not disclosed
    ("GPT-4", 2023.20, "https://arxiv.org/abs/2303.08774"),
    ("Claude 3", 2024.17, "https://www.anthropic.com/news/claude-3-family"),
    ("GPT-4o", 2024.36, "https://openai.com/index/hello-gpt-4o/"),
    ("Claude 3.5 Sonnet", 2024.47, "https://www.anthropic.com/news/claude-3-5-sonnet"),
    ("Claude Opus 4", 2025.39, "https://www.anthropic.com/news/claude-4"),
    ("GPT-5", 2025.60, "https://openai.com/index/introducing-gpt-5/"),
    ("GPT-6 Astra", 2026.67, "https://openai.com/index/gpt-6-astra/"),
    ("Claude Opus 5.5", 2026.72, "https://www.anthropic.com/claude-opus-5-5"),
]


def group_sizes():
    t = cache_get("tiny")
    cache_put("sizes", {"open": [list(r) for r in SIZES_OPEN], "closed": [list(r) for r in SIZES_CLOSED],
                        "tiny": ["our tiny GPT", 2026.82, t["params"]]})
    for r in SIZES_OPEN:
        print(f"  {r[0]}: {r[1]:.2f}, {r[2]:.3g} parameters" + (f", {r[3]:.3g} active" if r[3] else ""))
    print(f"  {len(SIZES_CLOSED)} closed models, sizes not disclosed")


# ------------------------------------------------------------------------ concepts
def group_concepts():
    # two explanatory sketches. look-back.png: attention, predicting the word after "too", looks
    # back at every earlier word and mostly at "water"; the weights are illustrative, not measured.
    # neglog.png: the loss for one prediction, -ln p of the true next token.
    words = ["The", "pump", "stopped", "because", "the", "water", "was", "too", "hot"]
    w = [0.04, 0.10, 0.12, 0.06, 0.08, 0.45, 0.10, 0.05]          # a sketch; they sum to 1
    dx, cur = 1.25, 7
    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.axis("off")
    ax.set_xlim(-0.7, (len(words) - 1) * dx + 0.7)
    ax.set_ylim(-0.9, 3.1)
    for i, wd in enumerate(words):
        x, future = i * dx, i > cur
        fc = "#f0f0f0" if future else ("#fbe3e7" if i == cur else "#dbe8f5")
        ec = "#c8c8c8" if future else (RED if i == cur else BLUE)
        ax.add_patch(plt.Rectangle((x - 0.55, -0.3), 1.1, 0.6, fc=fc, ec=ec, lw=2.2 if i == cur else 1.2))
        ax.text(x, 0, wd, ha="center", va="center", fontsize=14, color="#9a9a9a" if future else "#1a1a1a",
                fontweight="bold" if i == cur else "normal")
        if i < cur:
            arc = matplotlib.patches.FancyArrowPatch((cur * dx, 0.32), (x, 0.32),
                                                      connectionstyle=f"arc3,rad={0.18 + 0.025 * (cur - i)}",
                                                      arrowstyle="-|>", mutation_scale=12, lw=0.8 + 10 * w[i],
                                                      color=BLUE, alpha=0.3 + 0.7 * w[i] / max(w), zorder=0)
            ax.add_patch(arc)
            ax.text(x, -0.6, f"{w[i]:.0%}", ha="center", fontsize=12, color=BLUE)
    ax.text(cur * dx, -0.6, f"{w[cur]:.0%}", ha="center", fontsize=12, color=RED)
    ax.text(8 * dx, -0.6, "hidden", ha="center", fontsize=12, color="#9a9a9a")
    ax.text(-0.6, 2.95, 'predicting the word after "too": how much it uses each earlier word (a sketch)',
            fontsize=12.5, color="#5c5c5c", va="top")
    save(fig, "look-back.png")

    p = np.linspace(0.005, 1, 400)
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    ax.plot(p, -np.log(p), color=RED, lw=2.2)
    for pv, lab, off in [(1.0, "sure and right: 0", (-6, 14)), (0.5, "a coin flip: 0.69", (10, 6)),
                         (1 / 129, "a blind guess, 1/129: 4.86", (10, 6))]:
        ax.plot(pv, -np.log(pv), "o", color="#1a1a1a", ms=6)
        ax.annotate(lab, (pv, -np.log(pv)), xytext=off, textcoords="offset points", fontsize=11,
                    ha="right" if pv == 1.0 else "left")
    ax.set_xlabel("probability given to the true next token")
    ax.set_ylabel("loss, $-\\ln p$")
    ax.set_ylim(0, 5.6)
    ax.set_xlim(0, 1.05)
    save(fig, "neglog.png")


# ------------------------------------------------------------------------ chat
CHAT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"        # a small open chat model, Apache-2.0, about 1 GB
CHAT_SYSTEM = "You are a helpful assistant. Answer in one short sentence."


def group_chat():
    # a chat model is a next-token loop over a hidden script (the 3Blue1Brown "torn script"
    # idea, with a real model): the script it completes, and its top-5 next tokens at every
    # step of a greedy answer. A second question records a units slip.
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(4)
    tok = AutoTokenizer.from_pretrained(CHAT_MODEL)
    model = AutoModelForCausalLM.from_pretrained(CHAT_MODEL, dtype=torch.float32).eval()

    def answer(question, n=45):
        msgs = [{"role": "system", "content": CHAT_SYSTEM}, {"role": "user", "content": question}]
        script = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        ids = tok(script, return_tensors="pt").input_ids
        steps = []
        for _ in range(n):
            with torch.no_grad():
                p = torch.softmax(model(ids).logits[0, -1], -1)
            top = torch.topk(p, 5)
            steps.append([[tok.decode([int(i)]), round(float(v), 4)] for v, i in zip(top.values, top.indices)])
            nxt = int(top.indices[0])
            if nxt == tok.convert_tokens_to_ids("<|im_end|>"):
                break
            ids = torch.cat([ids, torch.tensor([[nxt]])], 1)
        return {"question": question, "script": script, "steps": steps,
                "answer": "".join(st[0][0] for st in steps[:-1])}

    out = {"model": CHAT_MODEL, "system": CHAT_SYSTEM,
           "chat": answer("In one sentence, what does a heat exchanger do?"),
           "units": answer("What is the boiling point of water at sea level?")}
    for key in ("chat", "units"):
        a = out[key]
        print(f"  {CHAT_MODEL}, {a['question']!r}: {a['answer']!r} ({len(a['steps'])} steps)")
    u = out["units"]["steps"]
    k = next(i for i, st in enumerate(u) if "Fahrenheit" in st[0][0] or "Celsius" in st[0][0])
    out["units"]["slip"] = k
    print(f"  the units step, after {''.join(st[0][0] for st in u[:k])!r}: {u[k]}")
    cache_put("chat", out)


# ------------------------------------------------------------------------ twoways
def abs_data(n=240, seed=16):
    # Lecture 16's data, y = |x| + noise, generated exactly as its make_figures.py does
    rng = np.random.default_rng(seed)
    x = rng.uniform(-1.2, 1.2, 4 * n)
    x = x[np.abs(x) >= 0.5][:n]
    return x, np.abs(x) + 0.03 * rng.standard_normal(n)


def group_twoways():
    # one distribution, sampled two ways: Lecture 16 draws a whole point (x, y) from its Gaussian
    # mixture; the autoregressive way draws x from p(x), then y from p(y | x)
    from scipy.stats import norm
    from sklearn.mixture import GaussianMixture
    x, y = abs_data()
    g = GaussianMixture(2, covariance_type="full", random_state=0, n_init=5).fit(np.column_stack([x, y]))
    w, mu, cov = g.weights_, g.means_, g.covariances_
    gx, gy = np.meshgrid(np.linspace(-1.4, 1.4, 240), np.linspace(-0.1, 1.45, 200))
    dens = sum(w[k] * np.exp(g._estimate_log_prob(np.column_stack([gx.ravel(), gy.ravel()]))[:, k])
               for k in range(2)).reshape(gx.shape)

    def p_x(v):
        return sum(w[k] * norm.pdf(v, mu[k, 0], np.sqrt(cov[k, 0, 0])) for k in range(2))

    def p_y_given_x(v, x0):
        a = np.array([w[k] * norm.pdf(x0, mu[k, 0], np.sqrt(cov[k, 0, 0])) for k in range(2)])
        a /= a.sum()
        m = [mu[k, 1] + cov[k, 1, 0] / cov[k, 0, 0] * (x0 - mu[k, 0]) for k in range(2)]
        sd = [np.sqrt(cov[k, 1, 1] - cov[k, 1, 0] ** 2 / cov[k, 0, 0]) for k in range(2)]
        return sum(a[k] * norm.pdf(v, m[k], sd[k]) for k in range(2))

    pts = g.sample(150)[0]
    x0 = 0.8
    ys = np.linspace(-0.1, 1.45, 400)
    cond = p_y_given_x(ys, x0)
    y0 = ys[np.argmax(cond)]
    fig, axes = plt.subplots(2, 2, figsize=(8.6, 3.9), sharex="col",
                             gridspec_kw={"height_ratios": [1, 3.2], "hspace": 0.05, "wspace": 0.12})
    axes[0, 0].axis("off")
    axes[0, 0].text(0.5, 0.15, "Lecture 16: a whole point at once", ha="center",
                    fontsize=14, transform=axes[0, 0].transAxes)
    for ax in axes[1]:
        ax.contour(gx, gy, dens, levels=dens.max() * np.array([0.03, 0.15, 0.4, 0.7]), colors=GRAY,
                   linewidths=0.8, alpha=0.7)
        ax.set_xlabel("x")
        ax.set_xlim(-1.4, 1.4)
        ax.set_ylim(-0.1, 1.45)
    axes[1, 0].scatter(pts[:, 0], pts[:, 1], s=9, color="k", alpha=0.6)
    axes[1, 0].set_ylabel("y")
    xs = np.linspace(-1.4, 1.4, 400)
    top = axes[0, 1]
    top.fill_between(xs, p_x(xs), color=BLUE, alpha=0.25)
    top.plot(xs, p_x(xs), color=BLUE)
    top.axvline(x0, color=RED, lw=2)
    top.set_yticks([])
    top.set_title("Autoregressive: one at a time", fontsize=14)
    top.spines["left"].set_visible(False)
    top.set_ylim(0, p_x(xs).max() * 1.45)
    top.text(0, p_x(xs).max() * 1.1, "1. x from p(x)", ha="center", color=BLUE, fontsize=13)
    ax = axes[1, 1]
    ax.axvline(x0, color=RED, lw=2, alpha=0.5)
    ax.fill_betweenx(ys, x0, x0 + 0.35 * cond / cond.max(), color=RED, alpha=0.25)
    ax.plot(x0 + 0.35 * cond / cond.max(), ys, color=RED)
    ax.plot([x0], [y0], "*", ms=18, color=RED, mec="k")
    ax.text(-1.35, 0.17, "2. y from p(y | x = 0.8)", color=RED, fontsize=13)
    ax.text(-1.35, 0.0, "p(x, y) = p(x) p(y | x)", fontsize=13)
    ax.set_yticklabels([])
    print(f"  Lecture 16's |x| data, 2-component mixture: weights {np.round(w, 2)}; "
          f"y given x = {x0}: peak at {y0:.2f}")
    save(fig, "two-ways.png")


# ------------------------------------------------------------------------ ar
def group_ar():
    # Lecture 8's AR(10) on reactor pressure, run recursively for two hours: each forecast is fed
    # back as an input, the way an LLM appends each token. Lecture 8's own loader and ridge are
    # reused, so the model is the one Lecture 8 measured.
    import importlib.util
    saved = dict(plt.rcParams)
    spec = importlib.util.spec_from_file_location("l08_figures", LECTURE.parent / "l08" / "figures" / "make_figures.py")
    l8 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(l8)
    plt.rcParams.update(saved)
    data = l8.runs_of(l8.ensure_fault_free())
    A, b, _ = l8.table(l8.TRAIN, data, 1)
    one = l8.Ridge().fit(A, b)
    H, t0, back = 40, 250, 40
    errs = {}
    for r in l8.TEST:
        y = data[r][l8.CH].to_numpy()
        z = y[t0 - np.arange(l8.P)][None, :]
        f = []
        for _ in range(H):
            nxt = one.predict(z)
            f.append(float(nxt[0]))
            z = np.column_stack([nxt, z[:, :-1]])
        errs[r] = (float(np.sqrt(np.mean((np.array(f) - y[t0 + 1:t0 + 1 + H]) ** 2))), f)
    order = sorted(errs, key=lambda r: errs[r][0])
    run = order[len(order) // 2]                     # the median run: neither the best nor the worst
    y = data[run][l8.CH].to_numpy()
    f = errs[run][1]
    dt = l8.DT
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    tb = np.arange(-back, 1) * dt
    ta = np.arange(1, H + 1) * dt
    ax.axvspan(-(l8.P - 1) * dt - 1.5, 1.5, color=BLUE, alpha=0.08)
    ax.plot(tb, y[t0 - back:t0 + 1], color="k", lw=1.4, label="measured")
    ax.plot(ta, y[t0 + 1:t0 + 1 + H], color=GRAY, lw=1.2, ls="--", label="what happened")
    ax.plot(ta, f, "o-", color=BLUE, ms=3.5, lw=1.4, label="recursive AR(10) forecast")
    ax.axhline(b.mean(), color=GOLD, ls=":", lw=1.4, label="mean of the training runs")
    lo, hi = ax.get_ylim()
    top = hi + 0.3 * (hi - lo)
    ax.set_ylim(lo, top)
    ax.text(-(l8.P - 1) * dt / 2, top, "last 10\nvalues:\ninputs", ha="center", va="top",
            fontsize=12, color=BLUE)
    ax.annotate("each forecast becomes\nan input for the next", (ta[8], f[8]), xytext=(ta[3], top),
                va="top", fontsize=12, color=BLUE, arrowprops=dict(arrowstyle="->", color=BLUE, lw=1))
    ax.set_xlabel("minutes from now")
    ax.set_ylabel("reactor pressure, kPa")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), fontsize=11, frameon=False, ncol=2)
    print(f"  AR(10), recursive, 2 h from sample {t0}: test run {run} (median of {len(order)} runs), "
          f"RMSE over the 2 h {errs[run][0]:.2f} kPa")
    save(fig, "ar-recursive.png")


# ------------------------------------------------------------------------ optmap
def group_optmap():
    # Lecture 15's sketch of where each optimizer fits, redrawn with the tiny GPT on it: 842,881
    # inputs (its parameters) and one gradient step in tens of milliseconds
    from matplotlib.patches import Rectangle
    t = cache_get("tiny")
    step_s = t["seconds"] / (t["steps"] + 1)
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(1, 1e12)
    ax.set_ylim(1e-4, 3e6)
    regions = [((1, 60), 20, 3e6, BLUE, "Bayesian optimization (Lecture 15)"),
               ((1, 1e-4), 1e12, 1, GREEN, "gradient-based: cheap steps, with gradients"),
               ((1, 1e-3), 300, 60, GOLD, "other derivative-free")]
    for (x0, y0), w, hgt, c, label in regions:
        ax.add_patch(Rectangle((x0, y0), w - x0, hgt - y0, fc=c, alpha=0.18, ec=c, lw=2, label=label))
    ax.plot(2, 3600 * 3, "*", color=GOLD, ms=16, mec="k", ls="none", label="Lecture 15's reactor: 2 knobs, hours each")
    ax.plot(t["params"], step_s, "*", color=RED, ms=20, mec="k", ls="none",
            label=f"our tiny GPT: {t['params']:,} parameters, {step_s * 1000:.0f} ms a step")
    ax.axvline(175e9, color=GRAY, ls="--", lw=1.2)
    ax.text(175e9 / 1.4, 2e-3, "GPT-3:\n175 billion\nparameters", ha="right", fontsize=10, color=GRAY)
    ax.legend(loc="upper right", fontsize=9.5, frameon=False, labelspacing=0.8)
    ax.set_yticks([1e-3, 1, 60, 3600, 86400, 6e5])
    ax.set_yticklabels(["1 ms", "1 s", "1 min", "1 h", "1 day", "1 week"])
    ax.set_xticks([1, 100, 1e4, 1e6, 1e8, 1e10, 1e12])
    ax.set_xticklabels(["1", "100", "10⁴", "10⁶", "10⁸", "10¹⁰", "10¹²"])
    ax.set_xlabel("number of inputs (decision variables)")
    ax.set_ylabel("cost of one evaluation")
    print(f"  tiny GPT: {t['params']:,} parameters, {step_s * 1000:.0f} ms per training step")
    save(fig, "decision-map.png")


# ------------------------------------------------------------------------ widget data
def write_widget_data():
    data = {}
    for name in ("bpe", "sample", "train", "learn", "examples", "chat", "terms", "sizes"):
        p = CACHE / f"{name}.json"
        if p.exists():
            data[name] = json.loads(p.read_text())
    text = ("/* Generated by lectures/l17/figures/make_figures.py. Do not edit. */\n"
            "window.COURSE_WIDGET_DATA = window.COURSE_WIDGET_DATA || {};\n"
            "window.COURSE_WIDGET_DATA.l17 = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n")
    WIDGET_JS.write_text(text)
    print(f"  wrote {WIDGET_JS.relative_to(REPO)} ({len(text) / 1024:.0f} KB)")


GROUPS = {"tiny": group_tiny, "tinyfig": draw_tiny, "bpe": group_bpe, "tokens": group_tokens, "gpt2": group_gpt2,
          "examples": group_examples, "scale": group_scale, "window": group_window,
          "optmap": group_optmap, "twoways": group_twoways, "ar": group_ar,
          "chat": group_chat, "concepts": group_concepts,
          "sizes": group_sizes}

if __name__ == "__main__":
    names = sys.argv[1:] or list(GROUPS)
    for name in names:
        print(f"[{name}]")
        GROUPS[name]()
    write_widget_data()
