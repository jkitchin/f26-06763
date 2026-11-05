# Lecture 20: Reinforcement learning, learning to act from rewards

:::{admonition} At a glance
:class: tip

- **Session** Lecture 20, Week 11 (optional)
- **Arc** Machine learning and deep learning
- **Slides** <a href="../../slides/l20/">Deck for this session</a>
- **Practice** <a href="../../game/#/l20">Practice module for this session</a>
- **Demo** [`l20-reinforcement-learning.ipynb`](l20-reinforcement-learning.ipynb), the three-level tank as
  matrices and Q-learning on it by hand, then tabular Q-learning on a tank against a tuned PID
  loop over ten seeds, each in seconds with NumPy alone
- **Tools** NumPy; Gymnasium and Stable-Baselines3 for the step beyond tables
- **Assignment** None. This session is optional and no assignment depends on it
:::

## Why this matters

In 2016 OpenAI trained an agent to play CoastRunners, a boat-racing video game, using the game's
score as the reward. The designers assumed that the score tracked progress around the course. The
agent found something else. In the authors' words, "The RL agent finds an isolated lagoon where
it can turn in a large circle and repeatedly knock over three targets", catching fire and
crashing as it circles, and it never finishes the race. It scored "on average 20 percent higher
than that achieved by human players"
([Clark and Amodei, 2016](https://openai.com/index/faulty-reward-functions/);
[archived copy](https://web.archive.org/web/2017id_/https://blog.openai.com/faulty-reward-functions/)).

Nothing in that agent was broken. It maximized exactly the number it was given, and the number
was not the goal. Every model in this course so far has been fitted to data that somebody
collected, against a loss that compares a prediction with a recorded answer. Reinforcement
learning (RL) drops both. The learner collects its own data by acting, and nobody tells it the
right action, only how well things went afterwards. That makes it able to learn behavior no
dataset contains, and it makes it able to learn the wrong behavior with great efficiency.

Engineers meet the same structure every day. A level controller chooses a valve position, and
the choice changes the level it will face at the next step. A battery scheduler that sells now
cannot sell the same energy tonight. When the decisions form a sequence and each one changes the
state of the system, the methods from earlier sessions do not fit, and reinforcement learning
does. It has real engineering successes. A network trained in simulation now shapes the plasma in
a Swiss tokamak, and an RL controller ran a distillation column for 35 days. It also has a cost
that the success stories rarely put in their headlines. The deep Q-network that learned Atari
games trained on about 38 days of game experience per game, against two hours of practice for
the human it was compared with
([Mnih et al., 2015](https://storage.googleapis.com/deepmind-media/dqn/DQNNaturePaper.pdf)).

This session starts with the mechanics and leaves the vocabulary for later. A tank small enough
to write as three numbers and two small matrices shows exactly what an action does to a system,
and a table of scores, trained by trying actions, shows where the choice of action comes from.
Only then does the session name the pieces, place reinforcement learning on the map of machine
learning the course has drawn, and ask why it is needed at all. It ends on the question an
engineer actually faces: when is learning from reward worth its cost, and when is a model and a
controller the better tool.

## Learning objectives

By the end of this session you should be able to:

- Write a small control problem as matrices, with where the system is as a vector of
  probabilities, each action as a matrix whose entries are the chances of moving between
  states, and the score of each move in a table, and take one step by multiplication.
- Explain how a rule for choosing actions is read from a table of action scores, and fill in
  that table by hand from rewards with the Q-learning update.
- Define reinforcement learning and its vocabulary: agent, environment, state, action,
  reward, policy, return, discount factor, value function, Q-function, episode, and
  exploration against exploitation (ε-greedy).
- Place reinforcement learning in the course's map of machine learning by the feedback the
  learner gets: a correct answer (supervised), samples of a distribution (generative), a score
  for one choice with no state (Bayesian optimization), or a score for a sequence of
  choices that change the system (reinforcement learning).
- Find the value of a state by adding up its discounted rewards, and the best action in each
  state by value iteration.
- Implement tabular Q-learning on tank level control and compare it with a tuned PID
  controller over several seeds.
- Say when reinforcement learning is the right tool and when a model with MPC, Bayesian
  optimization, or a tuned PID loop is, and read a published success claim for its baseline,
  seeds, sample count and simulator.

## How reinforcement learning works, with a tank

Before any of the field's vocabulary, here is a problem small enough to write on an index card: a
tank with three levels and a valve with two positions. Three things are needed to describe it.
Something to control, a way to write down where it is, and a way to write down what each choice
does to it. All three turn out to be ordinary arrays of numbers, and taking an action turns out to
be one matrix multiplication.

### The rules of a three-level tank

Picture an operator watching a tank that can be at one of three levels: low, ok or high. Each
minute the operator either opens the valve or shuts it. Opening raises the level one step, and
shutting lowers it one step; the level cannot go below low or above high. Landing at ok is what
the plant wants, so it earns a reward of +1. Opening the valve costs a little pumping energy, so
opening always costs 0.1. As in a real tank with a fixed menu of inflows, no action holds the
level at ok: opening from ok overshoots to high, and shutting from ok drops it to low.

That paragraph is everything the tank does, and it fits in six rows, one for each level and each
valve position:

| The tank is at | The operator | The tank moves to | Reward |
|---|---|---|---|
| low | shuts | low | 0 |
| low | opens | ok | +0.9 (the +1 for ok, less 0.1 for opening) |
| ok | shuts | low | 0 |
| ok | opens | high | −0.1 |
| high | shuts | ok | +1 |
| high | opens | high | −0.1 |

The figure below draws the same six facts as a diagram, one circle per level and one arrow per row of
the table. Read it like a board game: you are on a circle, you choose blue or orange, and you
follow that arrow and collect what is written on it. To know where you go next you need only
the circle you are on and the colour you choose; how you got to the circle never matters.

```{figure} figures/mdp-diagram.png
:alt: Three circles labelled low, ok and high. Blue arrows for open go from low to ok (reward +0.9), ok to high (reward minus 0.1), and high back to itself (minus 0.1). Orange arrows for shut go from low back to itself (reward 0), ok to low (0), and high to ok (+1.0).
:width: 90%

The three-level tank as a state diagram. Each arrow is one row of the table above. Drawn in
`figures/make_figures.py`.
```

### An action is a matrix

```{index} transition matrix
```

The table can be split by action. Take only the three rows where the operator shuts, and write
them as a grid with one row for where the tank is and one column for where it ends up, putting a
1 where it goes and a 0 everywhere else. Do the same for the rows where the operator opens. The
two grids are the tank's **transition matrices**, one per action. An action, in this
model, is a matrix:

$$
P_{\text{shut}} = \begin{bmatrix} 1 & 0 & 0 \\ 1 & 0 & 0 \\ 0 & 1 & 0 \end{bmatrix}, \qquad
P_{\text{open}} = \begin{bmatrix} 0 & 1 & 0 \\ 0 & 0 & 1 \\ 0 & 0 & 1 \end{bmatrix},
$$

with the rows and the columns both in the order low, ok, high. Every entry means something: the
row is where the tank is, the column is where it ends up, and the number is the chance of that
move. Row ok of $P_{\text{shut}}$ is $[1, 0, 0]$, which says "from ok, shutting takes you to
low," the third row of the table. Each row adds up to one, because the tank has to end up
somewhere.

:::{admonition} Definition: Transition matrix
:class: tip
A **transition matrix** $P_a$ holds, in row $i$ and column $j$, the probability that taking
action $a$ at level $i$ leads to level $j$; its rows sum to one.
:::

Here every probability is 0 or 1, because the tank is deterministic. A plant with noise has
rows that spread over several next states: if the valve sometimes sticks, row low of
$P_{\text{open}}$ might be $[0.2, 0.8, 0]$, meaning that opening from low reaches ok four times
in five and leaves the tank at low otherwise. The matrices then still say everything the
tank does, as probabilities.

### One step is a multiplication

That leaves the question of what the matrix acts on. Describe where the tank is with three
numbers, one per level, in the same order as the rows, each the chance that the tank is at that
level, so that they add up to one.
"Certainly at low" is $[1, 0, 0]$. An action then moves the tank by a single multiplication of that list by the
action's matrix:

$$
[\,1\ \ 0\ \ 0\,] \; P_{\text{open}} = [\,0\ \ 1\ \ 0\,].
$$

When the tank is certainly at one level, the multiplication does nothing more than pick out that
level's row of the matrix, and the row is where the tank goes. When the operator is unsure, say
equally likely low or ok, $[0.5, 0.5, 0]$, the same multiplication blends the two rows, half of
each, and opening gives $[0, 0.5, 0.5]$: equally likely ok or high. That is what it means, in
this model, for an action to change the system, exactly and completely: the action chooses which
matrix multiplies the three numbers.

The figure below lets you be the operator. In **Act** mode, press Open and Shut and watch the
three numbers pass through the matrix, the row being used shaded, and the rewards add up.

<div class="cw" data-widget="mdp-step" data-source="l20"></div>

### A score for every move

The last piece is the score. Each move earns a number, and those numbers also fit in a matrix,
one row per level and one column per action:

$$
R = \begin{bmatrix} 0 & 0.9 \\ 0 & -0.1 \\ 1 & -0.1 \end{bmatrix} \quad
(\text{rows: low, ok, high; columns: shut, open}).
$$

Opening from low earns 0.9, the +1 for reaching ok less the 0.1 for pumping, and shutting from
high earns +1. Run the tank for many minutes and add up the scores as they come, weighting a
score $k$ moves away by $0.9^k$:

$$
r_1 + 0.9\, r_2 + 0.9^2\, r_3 + \dots
$$

The weights do two jobs. A score now counts a little more than the same score much later, and an
endless run still adds up to a finite total. That total is the goal. Choosing the actions that
make it as large as possible is the whole problem, and every method in the rest of this session
is a way of doing it.

```{figure} figures/mdp-toy.png
:alt: Three small heat maps. P shut and P open are 3 by 3 matrices of zeros and ones; R is a 3 by 2 matrix of rewards
:width: 85%

The tank's two transition matrices and its reward matrix, the same six facts as the table and
the diagram. Computed in `figures/make_figures.py`.
```

## How the action gets chosen, and trained

```{index} Q-learning, greedy policy
```

The tank now has a description, but nothing yet decides what to do. Whatever decides needs a
rule, and the rule has to come from somewhere. This section shows where: from a second small
table, filled in by trying actions and keeping score.

### A rule is a table

For three levels, a rule for the valve is three entries: open at low, shut at ok, shut at high,
say. Once the rule is chosen, everything else follows. Start the tank anywhere, apply the rule,
and the matrices fix the path the tank takes and the total score it collects. The difficulty is
that nobody supplies the right entries. There is no teacher who says "at ok, you should have
shut"; the only feedback is the score of each move actually made. So the real question is how to
find a good rule from scores alone.

### A table of scores, and the larger one wins

The answer is a second table, called $Q$, with one number for each level and each action. For
the tank it is a 3 × 2 matrix:

$$
Q = \begin{bmatrix} Q(\text{low},\text{shut}) & Q(\text{low},\text{open}) \\
Q(\text{ok},\text{shut}) & Q(\text{ok},\text{open}) \\
Q(\text{high},\text{shut}) & Q(\text{high},\text{open}) \end{bmatrix}.
$$

Each entry says how good that move is, counting the score it earns now and the scores that can
follow from where it lands. With a good $Q$, choosing is a lookup: find the row for the current
level and take the column with the larger number, $a = \arg\max_a Q(s, a)$, which is called the
greedy choice. That is the same
final step as the classifier in [Lecture 10](../l10/notes.md), which scores every class and
reports the largest. The resemblance stops at where the numbers come from. A classifier's scores
are trained toward labels, the right class for each example. $Q$ has no labels. Its numbers are
estimates of future score, trained from the scores the moves actually earned, and the training
needs the numbers themselves as well as their order, because each update uses the best number in
the next row.

### Training the table: try, score, nudge

The training rule is short. Make a move, see the score $r$ it earned and the level $s'$ where it
landed, and nudge that one entry toward the score plus 0.9 times the best number in the new row:

$$
Q(s,a) \leftarrow Q(s,a) + \alpha \left[\, r + \gamma \max_{a'} Q(s',a') - Q(s,a) \right].
$$

Here $s$ is where the tank was, $a$ the move, $\gamma = 0.9$ the weight from the total score
above, and $\alpha$ how far each nudge goes. The bracket is the surprise: what this move suggests
the entry should be, minus what the table said. The best number in the new row is in the target
because a move is good either when it scores well now or when it lands somewhere from which good
moves are possible, and that second part is how a score earned later works its way back to the
moves that set it up. This rule is **Q-learning**
([Watkins and Dayan, 1992](https://www.gatsby.ucl.ac.uk/~dayan/papers/cjch.pdf), author's copy).

:::{admonition} Definition: Q-learning
:class: tip
**Q-learning** fills in the table of action scores from experience: after each move it nudges
that move's entry toward the score it earned plus the discounted best entry in the row where it
landed.
:::

### Training by hand


```{index} Q-table
```

Do it with numbers on the three-level tank. The program does not get to see the matrices or the
score table; it only sees the moves it makes. $Q$ is a 3 × 2 matrix, one row per level and one
column per action, and it starts at zero. Take $\alpha = 0.5$ and $\gamma = 0.9$.

The program starts at low and opens the valve. It lands at ok, so $r = 1 - 0.1 = 0.9$. The row
for ok is still all zeros, so the target is $0.9 + 0.9 \times 0 = 0.9$, the surprise is
$0.9 - 0 = 0.9$, and the entry moves halfway: $Q(\text{low}, \text{open}) = 0.45$. One
transition changed one number. The program then opens again from ok, overshoots to high, and pays
the 0.1 for opening, so $Q(\text{ok}, \text{open}) = 0.5 \times (-0.1) = -0.05$. From high it
shuts and lands at ok: $Q(\text{high}, \text{shut}) = 0.5 \times 1 = 0.5$.

The fourth update shows a later score working its way back. From ok the program shuts and
drops to low. The reward is 0, but the target is not: it is $0 + 0.9 \times \max(0, 0.45) = 0.405$,
because the first update taught the table that low is a good place to be when you can open
from there. So $Q(\text{ok}, \text{shut}) = 0.2025$, and the +1 that was earned by arriving at
ok from low has moved one step back, into the value of getting to low. When the program opens
from low a second time, the target is $0.9 + 0.9 \times 0.2025 = 1.082$, and
$Q(\text{low}, \text{open})$ climbs from 0.45 to 0.766, because the target now includes the
value of what follows. A sixth step, opening from ok to high again, finds
$\max Q(\text{high}, \cdot) = 0.5$ and lifts $Q(\text{ok}, \text{open})$ from −0.05 to 0.15.

| After | Q(low, shut) | Q(low, open) | Q(ok, shut) | Q(ok, open) | Q(high, shut) | Q(high, open) |
|---|---|---|---|---|---|---|
| 6 scripted updates | 0 | 0.766 | 0.203 | 0.150 | 0.500 | 0 |
| 306 updates | 4.261 | 4.735 | 4.261 | 4.238 | 4.831 | 2.479 |
| $Q^\ast$, the exact answer | 4.263 | 4.737 | 4.263 | 4.253 | 4.837 | 4.253 |

After 300 more steps, choosing at random one time in five as described below, the table is
within 0.02 of $Q^\ast$ in every entry but one. $Q^\ast$ is the exact answer, which the section
on values and planning computes directly from $P_{\text{shut}}$, $P_{\text{open}}$ and $R$. The exception is
$Q(\text{high}, \text{open})$, which was tried twice in 306 updates, because a program taking
the larger number at high shuts. The moves it would choose were right after the third update
and never changed.
The bigger tank later in this session shows the same thing: rarely visited entries are the last
to be right, and a table can act correctly long before every number in it is correct. Like the real
tank, no action holds the level at ok, so the best rule alternates, shutting from ok to low
and opening back. The figure steps through every update with its arithmetic.

<div class="cw" data-widget="q-hand" data-source="l20"></div>

```{figure} figures/qhand.png
:alt: Three 3 by 2 heat maps of Q values: after six scripted updates, after 306 updates, and Q star from value iteration
:width: 100%

The 3 × 2 Q matrix after the scripted episode, after 306 updates, and $Q^\ast$ from value
iteration. Bold marks the greedy action in each row. Computed in `figures/make_figures.py`.
```

### Explore sometimes

```{index} epsilon-greedy, exploration-exploitation trade-off
```

A program that always takes the larger number never tries the other move, and an entry that is
never tried is never learned, so it could keep a wrong guess forever. The fix is to choose the
larger number most of the time and a random move some of the time, for example one move in five.
This is **ε-greedy** choice with ε = 0.2. The walk-through above shows the cost of rarely trying
something: $Q(\text{high}, \text{open})$ was tried twice in 306 updates and is still far from its
exact value. The tension between using what the table already says and trying things to find out
is called exploration against exploitation.


## The words people use

```{index} reinforcement learning, Markov decision process, policy
```

```{index} see: RL; reinforcement learning
```

```{index} see: MDP; Markov decision process
```

Everything so far was a tank, three numbers, two matrices and two tables. The field has a name
for each of those, and the names are what papers and libraries use:

| Word | Means | In the three-level tank |
|---|---|---|
| state | where the system is | the level, or the three numbers |
| action | a choice that changes the state | open or shut, which picks $P_{\text{open}}$ or $P_{\text{shut}}$ |
| environment | everything the actions act on | the matrices $P_a$ and the scores $R$ |
| reward | the score of one move | one entry of $R$ |
| policy | the rule from state to action | low → open, ok → shut, high → shut |
| agent | the thing that chooses and learns | the program filling in $Q$ |
| episode | one run from a start to an end | one run of the tank |

The sentence that sounds vague at first, "the agent takes an action that affects the
environment", means only this: the program picks a matrix, and the matrix multiplies the state.
In the usual notation an **agent** observes the **state** $s_t$ of an **environment**, chooses an
**action** $a_t$, and receives a **reward** $r_{t+1}$ and the next state $s_{t+1}$. Its rule is
its **policy**, written $\pi(a \mid s)$ for the probability of each action in each state, and
one run from a start to an end is an **episode**.

:::{admonition} Definition: reinforcement learning
:class: tip
**Reinforcement learning** is learning which actions to take, in a system whose state the
actions change, from a numerical reward that scores the outcome instead of naming the correct
action.
:::

The whole setup has a name too. The tank's states, actions, matrices and scores together are a
**Markov decision process**.

:::{admonition} Definition: Markov decision process
:class: tip
A **Markov decision process** (MDP) is a set of states, a set of actions, transition
probabilities $p(s' \mid s, a)$ and a reward for each transition, where the next state depends
only on the current state and action, not on the earlier history.
:::

That last condition, the **Markov property**, is a modelling choice an engineer makes, and it
can be wrong. The tank's dynamics depend only on the current level, so its level is a Markov
state. A reactor whose next temperature depends on a catalyst that has been deactivating for a
week is not Markov in temperature alone; its state has to include the deactivation, or something
that tracks it. When a learned controller behaves strangely, a state that leaves out something
the dynamics depend on is one of the first things to check.

## Why reinforcement learning, when we already have machine learning

```{index} instructive feedback, evaluative feedback
```

This course has already used regression, classifiers, neural networks, Bayesian optimization
and generative models, so it is fair to ask what reinforcement learning adds. Machine learning
methods differ most in what the learner is told. [Lecture 9](../l09/notes.md)
divided the field into three types by the data: supervised learning has labels, unsupervised
learning has none, and reinforcement learning "takes actions in an environment, receives state
updates and feedback, and learns which actions pay off." This session fills in the third type,
and the clearest way to do it is by the feedback.

Sutton and Barto's textbook, the standard reference, puts the distinction in one sentence: the
most important feature of reinforcement learning "is that it uses training information that
evaluates the actions taken rather than instructs by giving correct actions"
([Sutton and Barto, 2018, ch. 2](http://incompleteideas.net/book/RLbook2020.pdf)). **Instructive
feedback** names the right answer whatever the learner did. Every regression and classifier in
[Lecture 9](../l09/notes.md) and [Lecture 10](../l10/notes.md) learned from it: the label is the
correct output, and the loss measures the distance to it. **Evaluative feedback** says how good
the chosen action was and nothing about the actions not chosen. A yield of 70% tells you that
catalyst B gave 70%. It does not tell you whether catalyst C would have given 74%.

```{figure} figures/landscape.png
:alt: A table of four methods. Supervised learning sees x and the right answer y star and is told the right answer; a decision is one prediction. Generative models see samples and are told nothing but to match the data. Bayesian optimization and active learning choose x and see y, a score for that choice, one experiment at a time with no state. Reinforcement learning acts and sees a reward and the next state; the score often arrives late and the action changes the state; a decision is a sequence.
:width: 100%

The course's methods sorted by what the learner is told. Generated by
`lectures/l20/figures/make_figures.py`.
:::

Read down the table and the problem gets harder in three distinct ways. [Lecture 16](../l16/notes.md)
placed generative models by what they learn, a whole distribution, and its learner is told only
to match the data. [Lecture 15](../l15/notes.md) moved to evaluative feedback: Bayesian
optimization chooses an experiment, measures its outcome, and chooses again. Its choices do not
change the system, though. Running a reaction at 80 °C today does not alter what 90 °C will give
tomorrow, so each experiment is a fresh decision with no state carried forward.

Reinforcement learning adds the two features Sutton and Barto call its most distinctive,
"trial-and-error search and delayed reward." The learner's action changes the state, and
through the state, every reward that follows. The consequence of an early choice can appear many
steps later, mixed with the consequences of every choice in between, which is called the
**credit assignment** problem. A level controller that opens the valve too far is not penalized
at that step. It is penalized several steps later, when the level overshoots.

<div class="cw" data-widget="rl-feedback" data-source="l20"></div>

The figure runs the same tank under each kind of learner. Under supervised learning the learner
receives pairs of a level and the correct inflow, which somebody had to know. Under Bayesian
optimization it tries one inflow, receives one score, and the tank starts over. Under
reinforcement learning it chooses an inflow at every step, the level it leaves behind is the
level it faces next, and the score accumulates over the whole run.

### The niche it fills

Reinforcement learning earns its cost when four things are true at once. The decisions come in a
sequence and each one changes the system the next one faces, which a model fitted once to a
dataset cannot represent. Nobody can label the right action, only score how things went. The
learner can try things cheaply, in a simulator, a game or a model of the plant, because it needs
many tries: the Atari DQN above trained on about 38 days of play per game. And the behavior
wanted is in no dataset, because nobody has produced it yet, so the learner has to collect its
own data by acting. Plasma shaping in a tokamak and tuning a language model to human preferences
meet all four. A controller for a plant that cannot be simulated cheaply usually fails the third,
and the limitations section below returns to what to use then.

### Where it meets language models

```{index} reinforcement learning from human feedback
```

```{index} see: RLHF; reinforcement learning from human feedback
```

The reinforcement learning most people have used without knowing it is inside a language
model. The model in
[Lecture 17](../l17/notes.md) is a next-token predictor fitted by supervised learning on text.
InstructGPT added two steps after that fit. The authors "train a reward model (RM) on this
dataset to predict which model output our labelers would prefer", and then "use this RM as a
reward function and fine-tune our supervised learning baseline to maximize this reward using the
PPO algorithm" ([Ouyang et al., 2022](https://arxiv.org/abs/2203.02155)). The result was striking:
outputs of their 1.3-billion-parameter model were preferred to those of the 175-billion-parameter
GPT-3. This is **reinforcement learning from human feedback** (RLHF), building on
[Christiano et al. (2017)](https://arxiv.org/abs/1706.03741). The environment is a learned reward
model standing in for a person's judgement, so everything this session says about rewards that
miss the intent applies to it.

## Values and planning

```{index} return, discount factor
```

When training filled in the $Q$ table by hand, its numbers crept toward an exact answer. When the
matrices are known, that answer can be computed directly, and computing it shows what training
was aiming at. This section also gives the formulas behind the 0.9 and the $Q$ table their usual
names.

### Return and discount

The total score from the first section has a name, the **return**, the discounted sum of
future rewards:

$$
G_t = r_{t+1} + \gamma\, r_{t+2} + \gamma^2 r_{t+3} + \dots = \sum_{k=0}^{\infty} \gamma^k r_{t+k+1}.
$$

The **discount factor** $\gamma$, between 0 and 1, sets how far ahead the agent looks. A reward
$k$ steps away counts $\gamma^k$ as much as one now, so the effective horizon is roughly
$1/(1-\gamma)$ steps. The three-level tank used $\gamma = 0.9$, about 10 steps. The PyCSE tank in the next
section uses $\gamma = 0.95$, which is 20 steps, or 10 time units, four times as long as that
tank takes to fill from 2 to 5 at full inflow. A $\gamma$ much smaller would make the agent
blind to the overshoot that its own valve opening causes.

### Values and the Bellman equation

```{index} value function, Q-function, Bellman equation, credit assignment
```

Two functions summarize how good things are under a policy. The **value function** $V^\pi(s)$ is
the expected return from state $s$ when following $\pi$. The **action-value function**, or
**Q-function**, $Q^\pi(s,a)$ is the expected return from taking action $a$ in state $s$ and then
following $\pi$. If you knew the Q-function of the best policy, $Q^\ast$, acting well would be
trivial: in each state, take the action with the largest $Q^\ast(s,a)$.

$Q^\ast$ satisfies a recursive relation called the **Bellman equation**, after Richard Bellman's
work on dynamic programming in the 1950s:

$$
Q^\ast(s,a) = \mathbb{E}\left[\, r_{t+1} + \gamma \max_{a'} Q^\ast(s_{t+1}, a') \;\middle|\; s_t = s,\ a_t = a \right].
$$

In words, the value of an action is its immediate reward plus the discounted value of the best
thing you can do from where it leaves you. Q-learning, from the training section above, is a way of solving this
equation from samples, without knowing $p(s' \mid s, a)$.

The equation also explains how a delayed reward reaches the decisions that earned it. Consider a
corridor of eight cells with a reward of +1 only on reaching the right end. After the first walk
down the corridor, only the last step knows about the reward. On the next walk, the step before
it reads that value through the $\max_{a'} Q$ term and learns that it leads somewhere good. Each
episode carries the news back one more cell, discounted by $\gamma$ each time.

```{figure} figures/credit.png
:alt: Value of stepping right in each of seven corridor cells after episodes 0 to 5. After episode 1 only cell 6 has value 1; each later episode extends the values one cell further left, approaching the dashed curve gamma to the power of the steps to go.
:width: 90%

One-step backups with α = 1 and γ = 0.9, sweeping the corridor from left to right. Generated by
`lectures/l20/figures/make_figures.py`.
:::

<div class="cw" data-widget="rl-credit" data-source="l20"></div>

This propagation is called **bootstrapping**: each estimate is updated from another estimate,
not from a complete observed return. It is why credit for a late reward reaches early decisions,
and it is also why it takes many episodes. A method that waited for the full return of each
episode, called Monte Carlo, would fill the whole corridor after one walk; it pays for that in
variance when the episodes are long and noisy.

### How good is a level? Follow the tank and add up the rewards

```{index} policy evaluation
```

Suppose the operator follows a simple rule: open when the tank is low, shut otherwise. Starting
at low, the tank goes low, ok, low, ok, and so on forever, and the rewards it collects are 0.9,
0, 0.9, 0, and so on. To turn that endless list into one number, count a reward $k$ steps in the
future as $\gamma^k$ times its size, with the discount factor $\gamma = 0.9$ from the first
section. The value of starting at low under this rule is then

$$
V(\text{low}) = 0.9 + 0.9 \times 0 + 0.9^2 \times 0.9 + 0.9^3 \times 0 + 0.9^4 \times 0.9 + \dots
= 0.9\,(1 + 0.81 + 0.81^2 + \dots) = \frac{0.9}{1 - 0.81} = 4.737,
$$

because the pattern repeats every two steps and each repeat is worth $0.9^2 = 0.81$ times the
last. Starting at ok, the first step is the one that earns nothing, so $V(\text{ok}) = 0.9 \times
4.737 = 4.263$. Starting at high, the operator shuts, earns +1 for reaching ok, and is then at ok:
$V(\text{high}) = 1 + 0.9 \times 4.263 = 4.837$.

These three numbers are the **value** of each level under the rule, and computing them is
called **policy evaluation**. Here it took one geometric series. For a table with thousands of
states the same bookkeeping becomes a set of simultaneous linear equations, one per state, which
a computer solves in one call. Sutton and Barto put it this way: when the dynamics are known,
the Bellman equation for the value of a rule "is a system of $|S|$ simultaneous linear equations
in $|S|$ unknowns"
([Sutton and Barto, section 4.1](http://incompleteideas.net/book/RLbook2020.pdf)).

### Which action is best? Compare, take the larger, repeat

```{index} value iteration, dynamic programming
```

The operator's real question is which action to take at each level, and the values answer it.
The worth of an action is the reward it earns now plus $\gamma$ times the value of the level it
leads to. At low, the two choices compare like this:

$$
Q(\text{low}, \text{shut}) = 0 + 0.9 \, V(\text{low}), \qquad
Q(\text{low}, \text{open}) = 0.9 + 0.9 \, V(\text{ok}),
$$

and the best action is whichever is larger. The value of a level is then the larger of its two
$Q$ numbers. That is the Bellman equation above, read out loud: an action is
worth its reward plus the best you can do from where it leaves you.

The equations refer to each other, so solve them by repetition. Start with every value at zero.
Compute every $Q$ from the current values, take the larger one in each row as the new values, and
do it again. Each pass is called a sweep, and the method is **value iteration**, one of the
dynamic-programming methods Richard Bellman introduced. After one sweep the values count one
step of reward, after two sweeps two steps, and so on:

| After | Q(low, shut) | Q(low, open) | Q(ok, shut) | Q(ok, open) | Q(high, shut) | Q(high, open) |
|---|---|---|---|---|---|---|
| 1 sweep | 0 | 0.9 | 0 | −0.1 | 1 | −0.1 |
| 2 sweeps | 0.81 | 0.9 | 0.81 | 0.8 | 1 | 0.8 |
| 3 sweeps | 0.81 | 1.629 | 0.81 | 0.8 | 1.729 | 0.8 |
| 263 sweeps | 4.263 | 4.737 | 4.263 | 4.253 | 4.837 | 4.253 |

The best action in each row, the larger number of each pair, is open at low and shut at ok and at
high from the very first sweep, long before the numbers themselves settle. After 263 sweeps nothing
changes in the twelfth decimal place, and the larger number in each row is exactly the value
found above by following the tank, 4.737, 4.263 and 4.837, because "open at low, shut otherwise"
is the best rule. In matrix form a sweep multiplies the current values by the same two matrices,
$P_{\text{shut}} V$ and $P_{\text{open}} V$, adds the rewards, and takes the larger entry in
each row. That maximum is the only part of the whole calculation that is not a multiplication or
an addition.

Switch the figure in the first section to **Plan** mode to run value iteration one sweep at a time, with the
arithmetic for row low written out on every step.

### What a learning agent does without the table

```{index} model-based reinforcement learning, model-free reinforcement learning, function approximation
```

Everything so far assumed you had the table. A plant does not come with one. That splits the
methods into two families. A **model-based** method gets the matrices, by being given them or by
counting what happens when it acts, and then plans with them exactly as above. A **model-free**
method never writes the matrices down. Sutton and Barto call model-free methods "explicitly
trial-and-error learners", the opposite of methods that plan with a model (section 1.3).

Q-learning, which filled in the table by hand earlier, is the model-free version of value
iteration. Value
iteration fills in $Q(\text{low}, \text{open})$ by looking up the row of $P_{\text{open}}$ to see
where opening leads. Q-learning has no row to look up, so it opens the valve, sees where the tank
actually went, and nudges that one entry toward the reward it got plus $\gamma$ times the best
value of where it landed. Sutton and Barto name the difference: "expected updates, considering
all possible events that might happen, or sample updates, considering a single sample of what
might happen" (section 8.5). The learned model is the same 3 × 2 table of $Q$ values; only the
way it is filled in differs.

When the states are too many to list, the table is replaced by a function that computes $Q$ from
a description of the state, a step called **function approximation**. A deep Q-network is that
function written as a neural network with one output per action, the "learned features followed
by a linear model" reading of a network in
[Kitchin, "Neural network interpretations"](https://kitchingroup.cheme.cmu.edu/posts/neural-network-interpretations/),
and the section on deep reinforcement learning below returns to it.

## Q-learning on a tank

```{index} temporal-difference learning
```

```{index} off-policy
```

The tank is the engineering example from the PyCSE chapter on reinforcement learning
([Kitchin, pycse](https://kitchingroup.cheme.cmu.edu/pycse/book/26-reinforcement-learning.html)),
used here with its parameters unchanged. A tank of cross-section $A = 1$ drains through an outlet
with flow $k\sqrt{h}$, $k = 0.5$, and the inflow $F$ is the action:

$$
\frac{dh}{dt} = \frac{F - k\sqrt{h}}{A}, \qquad F \in \{0, 0.5, 1.0, 1.5, 2.0\}.
$$

The controller's job is to hold the level at 5. The level is divided into 20 bins, which are the
states, and the reward is $-(h-5)^2 - 0.01 F^2$, the squared error plus a small charge for flow.
Episodes start at a random level between 1 and 9 and run for 100 steps of $\Delta t = 0.5$.

Q-learning works here exactly as on the three-level tank. The table of $Q(s,a)$ is now 20
states by 5 actions, 100 numbers, all starting at zero. After every step it nudges one entry
toward the Bellman target:

$$
Q(s,a) \leftarrow Q(s,a) + \alpha \left[\, r + \gamma \max_{a'} Q(s',a') - Q(s,a) \right].
$$

The bracket, the surprise from the hand-worked example, is called the **temporal-difference (TD)
error**: what the step suggested the value should be, minus what the table said. The learning rate $\alpha = 0.2$ sets how far each sample moves
the entry. The agent chooses actions **ε-greedily** with ε = 0.2: usually the best action in its
table, one time in five a random one, because the table can only learn about actions that get
tried. Watkins and Dayan's convergence proof holds "so long as all actions are repeatedly sampled
in all states and the action-values are represented discretely", which makes exploration a
mathematical requirement as well as a practical one.

The update uses the best next action, $\max_{a'}$, whatever action the agent will actually take
next. That makes Q-learning **off-policy**: it learns the value of acting greedily while behaving
ε-greedily.

### Five inflows are five columns

Choosing works as on the small tank: look up the row for the current level and take the column
with the largest value. The argmax explains why tabular Q-learning, and DQN after it, only handle
actions that can be listed. Five inflows are five columns. A valve that can sit anywhere between 0
and 2 has no columns to compare, and finding the best action would itself be an optimization at
every step. Continuous actions need the policy to output the action directly, which is the
subject of the section on deep reinforcement learning below.

With PyCSE's settings (1,000 episodes, α = 0.2, γ = 0.95, ε = 0.2), training takes 100,000
transitions and a fraction of a second. The total reward per episode rises from an average of
−33.8 over the first 50 episodes to −13.7 over the last 50.

<div class="cw" data-widget="tank-q" data-source="l20"></div>

In the figure, scrub through training and watch the table fill in. Early on, most states have no
preferred action. By the end, the policy column mostly says to open the inflow fully when the level is
low, close it when the level is high, and alternate around the setpoint. Look at the states near
the top of the tank, which training rarely visits: their entries are the last to settle, and in
some seeds they settle on the wrong action. The rollout panel runs
the greedy policy from the chosen start against a PID controller, and **Watch the test run**
plays that rollout on the tank one decision at a time. The stream from the faucet is as wide as
the inflow the table chose and the jet from the outlet is as wide as the outflow $k\sqrt{h}$, so
the level rises only while the stream in is wider than the stream out.

### Against PID, compared fairly

```{index} PID controller
```

PyCSE compares the trained agent with a PID controller using hand-picked gains,
$K_p = 0.8$, $K_i = 0.1$, $K_d = 0.2$, from one start at $h = 2$, and the agent wins. That
reproduces here. From $h = 2$ the agent's mean squared error is 0.22 across ten seeds, against 0.27
for that PID.

The comparison changes when it is made fairly. A fair comparison has three parts. The PID gains
should be tuned, which on this problem means a grid search of a few minutes over eight starting
levels (1, 2, 3, 4, 6, 7, 8 and 9). The test should use all eight starts. And the agent should be
trained with more than one seed. The table below has the results.

| Controller | MSE from h = 2 | MSE over eight starts |
|---|---|---|
| Q-learning, ten seeds | 0.22 (0.22 to 0.23) | 1.40 ± 1.31 (0.19 to 4.09) |
| PID, PyCSE's hand-picked gains (0.8, 0.1, 0.2) | 0.27 | 0.32 |
| PID, tuned on the eight starts (3.6, 0.3, 0) | 0.20 | 0.19 |
| Tuned PID forced onto the agent's five inflows | | 0.22 |

The tuned PID beats the agent from $h = 2$ and beats it by a factor of seven on average over the
eight starts. The agent's average hides two groups of seeds. Five of the ten learn a policy that
scores 0.19 to 0.21 over all eight starts, as good as the tuned PID and better than the PID
forced onto the same five inflows. The other five score 2.1 to 4.1, because each fails badly
from at least one start it rarely saw during training: seed 0's policy opens the inflow fully
at a level near 9, where it should close it. A coin flip decides whether training produces a
controller as good as a tuned PID loop or one that overfills the tank. One run from one start,
against a baseline nobody tuned, would have reported neither half of that.

```{figure} figures/tank-compare.png
:alt: Top, tank level from h equals 2 over 50 time units. Ten Q-learning seeds rise to 5 and then saw-tooth between about 4.7 and 5.2. PID with PyCSE gains rises slowly and reaches 5 near time 20. Tuned PID overshoots slightly, rings, and settles on 5 by time 15. Bottom, the agent's inflow jumps between 1.0 and 2.0 while the tuned PID's inflow settles at 1.118.
:width: 100%

The agent's ten seeds and two PID controllers from h = 2. Generated by
`lectures/l20/figures/make_figures.py`.
:::

The lower panel of the figure shows the second problem, which is in the action set. At steady
state the inflow equals the outflow, $F = k\sqrt{h}$, so holding $h = 5$ needs $F = 0.5\sqrt{5}
= 1.118$. The five allowed inflows hold steady levels of $h = (F/k)^2 = 0, 1, 4, 9$ and $16$, and
none of them is 5. No policy over this action set can hold the setpoint. The best it can do is
switch, and the trained agent does: in the last 40 steps of a run it uses inflow 1.0 35 times and
2.0 five times, switching ten times, so the level saw-tooths around 5. A real valve would wear
out doing that. The PID controller outputs a continuous inflow and settles at 1.118.

Refining the action set does not rescue the agent on the same budget. With nine inflows from 0 to
2, the mean squared error over the eight starts is 0.99 ± 0.94, because 180 table entries need
more experience than 100 and the training budget did not change. Discretization is a design
decision with a cost on each side, and a continuous action is one reason deep RL methods exist.

### What the table was estimating

The 20-bin tank can be written as matrices in the same way as the three-level one, which shows
what Q-learning was trying to estimate and separates the two reasons it lost. For each bin and
each of the five inflows, push 4,000 levels spread evenly across the bin through one step of the
tank's physics and record which bin each one lands in. The fractions are the row of $P_a$ for
that bin, and the mean reward is $R_{sa}$. The result is five 20 × 20 matrices.

The physics is deterministic, and the matrices are not. A bin hides where inside it the level
is, so two levels in the same bin can land in different bins after one step. With the inflow at
1.0, a level in bin 9, between 4.74 and 5.26, stays in bin 9 with probability 0.911 and falls
to bin 8 with probability 0.089. Every row of every matrix splits over at most two next bins,
and most of the mass sits on the diagonal, because half a time unit moves the level less than a
bin. The randomness is a property of the state chosen, the 20 bins, and that is the Markov
property from earlier in a concrete form: the bin is only approximately Markov, because the
level inside it also matters.

Value iteration on these matrices takes 386 sweeps and gives a bang-bang policy: full inflow
below the setpoint bin, 1.0 in it, and shut above it. Rolled out on the continuous tank, that
policy scores a mean squared error of 0.187 over the eight starts and 0.22 from $h = 2$, as good
as the tuned PID loop's 0.19 and the best Q-learning seed. So the five inflows, the 20 bins and
the 100-entry table were enough, and the five failing seeds failed at learning.

The matrices also show how they failed. Every seed, good or bad, disagrees with the exact policy
in two to five bins, mostly at the bottom of the tank (bins 0 and 1, below $h = 1.05$) and the
top (bins 17 and 18), which episodes starting between 1 and 9 rarely reach. What separates the
bad seeds is which wrong action they picked. Seeds 2, 3 and 8 choose inflow 0.5 in bin 1, and
seeds 2 and 4 choose 1.5 in bin 17; seed 2, with both, is the worst of the ten at 4.08. Those are the two inflows that hold the level inside the same
bin, since 0.5 holds $h = 1$ and 1.5 holds $h = 9$, so the corresponding entries of $P_{0.5}$
and $P_{1.5}$ are exactly 1 on the diagonal. From a start of 1 or 9, the tank parks there for
all 100 steps and scores $(5 - 1)^2 = (9 - 5)^2 = 16$. Seed 0 opens fully in bin 17 and overfills the tank
from 9. The good seeds chose wrong actions in the same rarely visited bins, but none that traps
the level. The figure shows the disagreement.

```{figure} figures/tank-matrices.png
:alt: Left and middle, two 20 by 20 heat maps of transition probabilities for inflows 0 and 1, both concentrated on a band along the diagonal. Right, inflow chosen against level for value iteration, a staircase from 2 down to 0 at the setpoint, with green dots for ten Q-learning seeds that agree in the middle and scatter at the lowest and highest levels
:width: 100%

The 20-bin tank as transition matrices for two of its five inflows, and the greedy policy from
value iteration on all five against the policies Q-learning learned in ten seeds. Computed in
`figures/make_figures.py`, assuming levels spread evenly inside each bin.
```

The same experiment can be run the model-based way on the same budget. Take 100,000 transitions
with random inflows, the number Q-learning trained on, count them into $\hat P_a$ and $\hat R$,
and run value iteration on the estimates. Across ten seeds the resulting policy scores 0.187
over the eight starts every time, against Q-learning's 1.40 ± 1.31, even though 8 to 14 of the
100 state-action pairs were never visited at all. A model fitted to the data and then solved
made far better use of the transitions than the sample updates did. The limitations section
below returns to this, because it is the typical result on control problems where a model can
be fitted.

### Changing the reward

```{index} specification gaming
```

```{index} see: reward hacking; specification gaming
```

```{index} pair: failure mode; specification gaming
```

The reward is the only description of the goal the agent ever sees, so a reward that a
reasonable engineer might write can still describe a different goal. Two examples, with
everything else unchanged.

"Keep the level steady" sounds like a description of good level control. As a reward it is
$-|h_{t+1} - h_t|$, a penalty on movement. The trained agent satisfies it perfectly: it parks the
tank at whichever constant-inflow steady state is nearest, 1, 4 or 9, and leaves it there.
Started at 8, it sets the inflow to 1.5 and lets the level settle at 9. The level is very steady
and the setpoint was never mentioned, so the mean squared error from 5 is 9.69.

"+1 for every step inside 5 ± 1" gives no credit for being nearer 5 than 4.1. The trained agent
holds the level between about 4.2 and 4.7 and never aims for 5, because nothing in the reward
says 5 is better than 4.3.

```{figure} figures/tank-hacks.png
:alt: Left, under the reward minus the absolute change in level, the tank started at 8 rises smoothly to 9 and stays there, far from the setpoint of 5. Right, under a reward of 1 inside the band from 4 to 6, the level rises from 2 to about 4.3 and then saw-tooths between 4.2 and 4.7 inside the lower half of the band.
:width: 100%

The same agent and tank under two rewards that are reasonable descriptions of the goal and not
the goal itself. Generated by `lectures/l20/figures/make_figures.py`.
:::

This is **specification gaming**, which Krakovna and colleagues at DeepMind define as "a
behaviour that satisfies the literal specification of an objective without achieving the
intended outcome" ([Krakovna et al., 2020](https://deepmind.google/discover/blog/specification-gaming-the-flip-side-of-ai-ingenuity/)).
Their list collects around 60 examples. The CoastRunners boat is one, and the tank is a small,
fully explainable one. The optimizer is not malfunctioning in any of them. It is doing its job on
the wrong objective.

:::{admonition} What a practitioner should take from this
:class: tip
Compare against a baseline someone actually tuned, from every start you care about, over several
training seeds, and report the spread along with the mean. Check that the action set can reach
the target at all, and think through what it costs the equipment to switch. Write the reward,
then train on it and watch the behavior. The trajectory shows what the reward actually asks for,
which a plot of the total reward cannot.
:::

## Deep reinforcement learning and the tools

```{index} deep reinforcement learning, DQN, PPO, Gymnasium, Stable-Baselines3
```

A table works when the states and actions can be listed. A tank with 20 bins can be; a camera
image or the 19 coil currents of a tokamak cannot. **Deep reinforcement learning** replaces the
table with a neural network of the kind built in [Lecture 11](../l11/notes.md). The deep
Q-network (DQN) of [Mnih et al. (2015)](https://storage.googleapis.com/deepmind-media/dqn/DQNNaturePaper.pdf)
approximated $Q(s,a)$ from raw Atari screen pixels. Two stabilizers made it train: a replay
buffer of past transitions sampled at random, which breaks the correlation between successive
steps, and a target network updated only periodically. It reached more than 75% of the human
tester's score on 29 of the 49 games.

The cost is in the same paper. Each game was trained on "a total of 50 million frames (that is,
around 38 days of game experience in total)", while the professional human tester had "around 2
h of practice playing each game." The gap has narrowed since, and it has not closed. Writing in
2018, Irpan noted that Rainbow DQN reached the human threshold after about 18 million frames, or
roughly 83 hours of play ([Irpan, 2018](https://www.alexirpan.com/2018/02/14/rl-hard.html)).

Policy-gradient methods learn the policy directly instead of a value table. The most widely used
is **proximal policy optimization** (PPO; [Schulman et al., 2017](https://arxiv.org/abs/1707.06347)),
which limits how far each update can move the policy, and which InstructGPT used.

### Continuous actions: a policy that outputs the inflow

```{index} policy gradient, Gaussian policy, REINFORCE
```

A policy network has to end in something that produces an action, and there are three common
endings. A Q-network ends in one output per action and the agent takes the argmax, exactly as
the table did. A policy for discrete actions ends in a softmax, the same layer that ends the
classifiers of [Lecture 10](../l10/notes.md), and the agent samples an action from the
probabilities, which gives it a built-in way to explore. A policy for continuous actions ends
in two numbers, the mean and the spread of a Gaussian, and the agent samples the action from
that distribution. Stable-Baselines3 documents exactly this: for continuous actions "the policy
network outputs mean and (log) std of the distribution", and for discrete actions it "outputs
probability of taking each action"
([Stable-Baselines3, probability distributions](https://stable-baselines3.readthedocs.io/en/master/common/distributions.html)).
At deployment the agent usually takes the mean and stops sampling.

```{figure} figures/action-heads.png
:alt: Three panels. A bar chart of five Q values with the largest in red; a bar chart of softmax probabilities over the same five inflows; a Gaussian density over inflow with the clipped regions shaded
:width: 100%

Three ways to turn a state into an action, near the setpoint of the tank. Left: the row of a
trained Q-table, and the argmax. Middle: a softmax of the same row at temperature 0.1, which is
sampled. Right: the Gaussian policy trained below, at h = 4.8, which is sampled and then
clipped to the valve's range. Computed in `figures/make_figures.py`.
```

The softmax ending looks like a classifier, and it is trained like one with a twist. A
classifier raises the log-probability of the labelled class. A **policy gradient** method
raises the log-probability of the action the agent actually took, weighted by how much better
than average the return after it turned out to be. Actions followed by good outcomes become
more likely and actions followed by bad ones less likely, with the agent's own experience in
place of labels. The simplest version is Williams's REINFORCE
([Williams, 1992](https://people.cs.umass.edu/~barto/courses/cs687/williams92simple.pdf), a course copy of the *Machine Learning* paper), and PPO is a more
careful descendant of the same idea.

To see this on the tank, give the policy a Gaussian with a fixed spread $\sigma = 0.3$ and a
mean that is a straight line in the error, $\mu = \theta_0 + \theta_1 (5 - h)$. That is two
parameters, and nothing tells the policy what they should be. Training them by REINFORCE on
the same reward, ten episodes per update for 300 updates, ten seeds, learns a $\theta_0$
between 1.02 and 1.26 in nine of the ten seeds. The inflow that holds the level at 5 is
$k\sqrt{5} = 1.118$, so the policy found the holding inflow from reward alone. Deployed with
its mean action, it scores a mean squared error of 0.176 ± 0.025 over the eight starts, against
0.189 for the tuned PID and 1.40 for the Q-table.

```{figure} figures/policy-gradient.png
:alt: Left, inflow against level for the Q-table policy, a staircase, and the Gaussian policy mean, a clipped straight line; right, learning curves of ten seeds rising from about minus two thousand to about minus ten
:width: 100%

Left: the policy as a function of the level. The Q-table (one seed) can only choose among
five inflows, and in the rarely visited bins above 9 and below 0.5 it chooses badly. The
Gaussian policy's mean (the median seed) is a clipped line through the holding inflow. Right:
mean episode reward during policy-gradient training, ten seeds. Computed in
`figures/make_figures.py`.
```

Two things keep this from being a clean win for reinforcement learning. The policy's form,
a line in the error from the setpoint, is a proportional controller with a feedforward term,
so the engineering knowledge was put in by whoever chose the features, as it is in a PID loop.
And it used 300,000 transitions, three times the Q-table's budget, to tune two numbers that a
control engineer would set from the steady-state balance and a step test. What it does show is
the mechanism by which PPO and its relatives handle a continuous valve: the network outputs the
parameters of a distribution, and reward reshapes that distribution.

### The standard libraries

```{index} RLlib, TRL
```

Nobody writes these algorithms from scratch for a real problem. The landscape has settled into
a few libraries with distinct jobs:

| Library | What it is for |
|---|---|
| [Gymnasium](https://gymnasium.farama.org/) | The environment interface (`reset`, `step`) and reference environments; "a maintained fork of OpenAI's Gym library" |
| [Stable-Baselines3](https://stable-baselines3.readthedocs.io/en/master/guide/algos.html) | Tested PyTorch implementations of A2C, DDPG, DQN, HER, PPO, SAC and TD3; the place to start |
| [RLlib](https://docs.ray.io/en/latest/rllib/index.html) | Ray's library for "production-level, highly scalable, and fault-tolerant RL workloads", multi-agent and offline data |
| [CleanRL](https://docs.cleanrl.dev/) | "single-file implementation" of each algorithm, for reading and modifying the code |
| [TorchRL](https://docs.pytorch.org/rl/stable/index.html) | PyTorch's own building blocks for writing new algorithms |
| [TRL](https://huggingface.co/docs/trl/index) | Hugging Face's library for training language models with SFT, reward modeling, DPO and GRPO |
| [PettingZoo](https://pettingzoo.farama.org/) | "An API standard for multi-agent reinforcement learning", from the Farama Foundation, which also maintains Gymnasium |

Stable-Baselines3's algorithm table is the quickest check of which algorithm fits which
problem: DQN accepts only discrete actions, SAC, TD3 and DDPG only continuous ones, and PPO
both. For the tank with a continuous valve that means PPO or SAC; with five inflows, DQN or
PPO. TRL is the library for the language-model side, the RLHF described earlier in these notes.

For an engineer, the practical route is the first pair.
[Gymnasium](https://gymnasium.farama.org/), "a maintained fork of OpenAI's Gym library", defines
the environment interface, and [Stable-Baselines3](https://stable-baselines3.readthedocs.io/)
provides "reliable implementations of reinforcement learning algorithms in PyTorch", among them
DQN, PPO, SAC and TD3. The contract between the two is one method, `step`:

```python
obs, reward, terminated, truncated, info = env.step(action)
# terminated: the episode reached a real end (goal, failure)
# truncated:  it was cut off (a time limit); the value of obs still matters
```

The `terminated` and `truncated` flags exist because the Bellman target differs between them.
After a real end there is no future value to add. After a time limit there is, and an
implementation that treats a time limit as a true end teaches the agent that the world stops
at step 100. Wrapping the tank as a Gymnasium environment with a continuous inflow in $[0, 2]$
and training PPO on it is about a dozen lines with these libraries, and it removes the five-valve
limitation. The optional last cell of the notebook does this: one PPO run, one seed, 50,000
steps, scored 0.165 over the eight starts against the tuned PID's 0.189. That is one seed, so it
is the start of an answer. The same three checks as before decide whether it is a result.

## Case studies

Each case below is documented in a primary source and teaches something specific about where
reinforcement learning works. Two of them also teach how a number drifts away from its source.

### Magnetic control of a tokamak

```{index} pair: case study; TCV tokamak magnetic control
```

A tokamak confines plasma with magnetic fields, and the shape of the plasma is set by currents in
many coils that have to be adjusted continuously. [Degrave et al. (2022)](https://www.nature.com/articles/s41586-021-04301-9)
trained one neural network to drive all 19 coils of the TCV tokamak in Lausanne at 10 kHz. It was
trained entirely in a simulator, using "5,000 actors in parallel" with "training times of 1-3
days", and transferred to the hardware with no further training, "zero-shot". It produced
standard elongated shapes, negative triangularity, a snowflake configuration, and two separate
plasmas, "droplets", held in the vessel at once.

The advantage was in redesign. Conventional controllers "require
substantial engineering effort, design effort and expertise whenever the target plasma
configuration is changed." Reinforcement learning changed that design loop: specify a new shape
as a reward, and train. It depended completely on a simulator accurate enough that a policy
trained in it worked on the machine.

### A distillation column for 35 days

```{index} pair: case study; Yokogawa and JSR distillation control
```

In 2022 Yokogawa and JSR announced that an RL controller had run a distillation column at a JSR
chemical plant "for 35 days, from January 17 to February 21, 2022 (840 hours)", holding the
column's liquid level while maximizing the use of waste heat, with "basically, no human
intervention" ([Yokogawa, 2022](https://www.yokogawa.com/news/press-releases/2022/2022-03-22/)).
The algorithm, FKDPP, came from Yokogawa and the Nara Institute of Science and Technology, and
training used the OmegaLand plant simulator. The application targeted operations previously
run by hand because they were "beyond the capabilities of existing control methods (PID
control/APC)."

Read the source for what it leaves out. It is a vendor press release, it reports no energy or
yield figures, and its "world first" rests on the company's own survey. The run is a real
milestone, and it shows that an RL controller can operate a unit safely for weeks. How much
better it was than the previous manual operation is unknown, because no comparison is
published.

### Optimizing reactions, without a Bayesian baseline

```{index} pair: case study; deep reaction optimizer
```

[Zhou, Li and Zare (2017)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5746857/) framed reaction
optimization as reinforcement learning. The state is the history of conditions tried and results
measured, the action is the next set of conditions, and the policy is a recurrent network
pretrained on simulated response surfaces. The abstract reports that the method "outperformed a
state-of-the-art blackbox optimization algorithm by using 71% fewer steps."

The body says where the 71% comes from: on simulated mixtures of Gaussians, it reached the
regret criterion "in approximately 32 steps, on average, whereas CMA-ES needs 111 steps", and
1 − 32/111 is 71%. The figure is from simulated test functions, against CMA-ES, an evolutionary
optimizer. The paper does not compare against Bayesian optimization, the method
[Lecture 15](../l15/notes.md) built for exactly this problem, and the word "Bayesian" does not
appear in it. The problem has no state that the experiments change, which puts it in the
Bayesian optimization row of the methods table. The RL framing works, and the comparison a reader most needs is missing.

### Data-centre cooling: a number that drifted

```{index} pair: case study; Google data-centre cooling
```

The claim that "DeepMind used reinforcement learning to cut Google's data-centre cooling by 40%"
is widely repeated. The 2016 source is a blog post. It reports that a system could "reduce the
amount of energy we use for cooling by up to 40 percent" using ensembles of neural networks
trained on historical sensor data to predict future conditions and recommend actions
([Evans and Gao, 2016](https://deepmind.google/discover/blog/deepmind-ai-reduces-google-data-centre-cooling-bill-by-40/)).
The post never uses the words "reinforcement learning".

The peer-reviewed follow-up is [Lazic et al. (2018)](https://proceedings.neurips.cc/paper/2018/hash/059fdcd96baeb75112f09fa1dcc740cc-Abstract.html),
and it is model predictive control: "we learn a linear model of the DC dynamics using safe,
random exploration", from three hours of exploration data, and "re-optimize at each time step."
Its claim is that the controller "has the potential to save about 9% of the current server-floor
cooling costs", against local PID loops. The same paper reports that a model fitted to a week of
the PID loops' own history did worse. In its words, the loops "operate in too narrow a range" to
generate data for identification, which is [Lecture 7](../l07/notes.md)'s closed-loop problem in
production. The honest summary is a learned linear model plus MPC, with an expected saving of
around 9%.

:::{admonition} What a practitioner should take from this
:class: tip
Before trusting a reinforcement learning result, find four things in the primary source. What was
the baseline, and was it tuned? How many seeds, and what was the spread? How many samples did
training use, and what would that many cost on your equipment? Where did training happen, and
what is the evidence that the simulator matches the plant? A claim that answers all four is rare,
and it is worth more than a large number that answers none.
:::

## Limitations and trade-offs

```{index} sim-to-real gap, domain randomization, model predictive control
```

```{index} see: MPC; model predictive control
```

**Samples are expensive.** The tank needed 100,000 transitions for a 100-entry table, and DQN
needed 38 days of play per game. Reinforcement learning gets its data by acting, and acting is
the expensive part of most engineering systems. In a simulator the cost is compute. On a plant
it is product, time and risk.

**Results vary by seed.** [Henderson et al. (2018)](https://arxiv.org/abs/1709.06560) ran ten
trials of the same configuration, changing only the random seed, split them into two groups of
five, and found "the variance between runs is enough to create statistically different
distributions just from varying random seeds." The tank's eight-start error ranged from 0.19 to
4.09 across ten seeds. A result from one seed is an anecdote, which is the rule
[Lecture 15](../l15/notes.md) gave for Bayesian optimization.

**The reward is the specification.** Anything the reward leaves out, the agent is free to
sacrifice, and anything it rewards by accident, the agent will find. RLHF inherits this, with a
learned reward model in place of a hand-written one.

**Simulators are not plants.** The difference between them is called the **sim-to-real gap**.
Most engineering successes, the tokamak and the distillation
column included, trained in a simulator and transferred. A policy can exploit a simulator's
errors as readily as a reward's. **Domain randomization** trains across many randomized
versions of the simulator: "With enough variability in the simulator, the real world may appear to
the model as just another variation" ([Tobin et al., 2017](https://arxiv.org/abs/1703.06907)).
That paper randomized textures to train object localization for a robot arm; the same idea is
used to train controllers.

**Exploration can be unsafe.** ε-greedy is not acceptable on equipment that can be damaged. A
control system cannot take a random move one time in five to find out where the edge of safe
operation is, and this is the main reason reinforcement learning for real equipment is trained in
a simulator. The alternative is to learn from logged operating data, which is off-policy learning in its
purest form. It runs straight into the problem [Lecture 7](../l07/notes.md) called
closed-loop identification: data recorded while a controller was holding the plant steady
contains little information about what happens anywhere else. Google's 2018 data-centre
controller found exactly this when it tried to fit a model to a week of historical data from its
PID loops, as the data-centre case study above describes.

**A model often wins.** When you have a dynamic model, even an approximate one, model-based
control is usually far more sample-efficient. Recht's review of RL from the view of control
theory found that "the so-called 'model-free' methods popular in deep reinforcement learning are
considerably less effective in both theory and practice than simple model-based schemes when
applied to LQR," and that "Policy gradient, in particular requires thousands of times as many
samples as simple nominal control" ([Recht, 2019](https://arxiv.org/abs/1806.09460)). The tank
showed the same thing on a small scale: the 100,000 transitions that gave Q-learning 1.40 ± 1.31
gave 0.187 on every seed once they were counted into transition matrices and solved. The same
review notes that approximate dynamic programming "is closely related to canonical receding
horizon control (RHC) (also known as Model Predictive Control (MPC))." **Model predictive control**
fits a model, optimizes the actions over a horizon, applies the first one, and repeats. It is the
engineer's usual answer to a sequential decision problem with a model. Reinforcement learning is
its close relative, and the better choice only when no usable model exists and a simulator
does.

| The problem | The usual tool |
|---|---|
| One loop, a setpoint, dynamics that are roughly linear | PID, tuned |
| Several interacting variables, constraints, a model you can fit | MPC |
| Choose the next experiment; outcomes do not change the system | Bayesian optimization (L15) |
| A sequence of decisions, an accurate simulator, a controller hard to design by hand or redesigned often | reinforcement learning |
| No simulator, and exploring on the real system is unsafe | not reinforcement learning |

The PyCSE chapter lists the same conditions from the other side, including "When you have a good
mathematical model and can use optimization directly" and "When you can't simulate or the real
system is too expensive to experiment on."

## In-class demo

The notebook [`l20-reinforcement-learning.ipynb`](l20-reinforcement-learning.ipynb) runs the
examples with NumPy alone in about three minutes. It starts with the three-level tank written as
matrices, solved by a linear solve and by value iteration, then prints every number of the first six Q-learning updates on the
three-level tank and compares the result with $Q^\ast$. Then it trains tabular Q-learning on the
PyCSE tank, tunes a PID loop on the spot, and compares them over ten seeds and eight starts. It
changes the tank's reward twice and prints where the agent leaves the level, and trains the Gaussian policy on the tank with REINFORCE for
three seeds. An optional
last cell wraps the tank for Gymnasium and trains PPO if Stable-Baselines3 is installed. The
figures in these notes run the same code in the browser, so you can retrain each example with a
different seed.

## Summary

Reinforcement learning fits in a few arrays. Where a system is can be written as a vector of
probabilities, each action as a matrix whose entry in row $i$ and column $j$ is the chance that
the action takes the system from $i$ to $j$, and taking an action as one multiplication of the
vector by that matrix. Each move earns a score, and the goal is the largest total of discounted
scores. The choice of action comes from a table $Q$ of scores, one per state and action, read by
taking the larger number in the row, and the table is trained by trying moves and nudging each
entry toward the score it earned plus the best entry where it landed, which is Q-learning. Only
then do the field's words attach to things already computed: state, action, environment, reward,
policy, agent, and the Markov decision process that holds them. Reinforcement learning fills the
niche where decisions come in a sequence and change the system, nobody can label the right
action, and trying things is cheap. With the matrices known, the value of a state is its discounted rewards added up, and value
iteration finds the best action by comparing, taking the larger, and repeating; Q-learning
reaches the same table from samples without ever forming the matrices. On the PyCSE tank it beat a PID loop with untuned
gains from one start, and it lost to a tuned PID loop across eight starts and ten seeds. Its
five inflows could not hold the setpoint, which made the level saw-tooth, but solving the
tank's own transition matrices exactly gave a policy over the same five inflows that matched
the tuned PID loop. The loss came from learning: half the seeds picked, in a rarely visited
bin, an inflow that parks the tank there. A reward that said "keep it steady" produced a steady tank at the
wrong level. Exploring means taking random moves on the
equipment, which is why real controllers are trained in simulators. The successes are real, the
tokamak above all, and they share an accurate simulator and a controller that was hard to
design by hand. Without those, a model with MPC, a tuned PID loop, or Bayesian optimization is
usually the better tool. Every published claim deserves four questions: baseline, seeds,
samples and simulator.

## Resources

- [Sutton and Barto, *Reinforcement Learning: An Introduction*, 2nd ed.](http://incompleteideas.net/book/RLbook2020.pdf)
  (MIT Press, 2018, free from the authors). The standard text; chapters 1, 2 (evaluative feedback), 3 (MDPs),
  4 (dynamic programming: policy evaluation as a linear system, and value iteration) and 6 (TD
  learning and Q-learning) cover this session, and section 8.5 sets expected
  updates against sample updates.
- [Kitchin, "Neural network interpretations"](https://kitchingroup.cheme.cmu.edu/posts/neural-network-interpretations/).
  A network read as learned features followed by linear regression; the matrix section here does
  the same for a Markov decision process, and the reading carries over to a deep Q-network.
- [Kitchin, *pycse*, "Reinforcement learning"](https://kitchingroup.cheme.cmu.edu/pycse/book/26-reinforcement-learning.html).
  The tank, grid world, battery scheduling, and a "when not to use RL" list, in Python.
- [OpenAI, Spinning Up in Deep RL, part 1](https://spinningup.openai.com/en/latest/spinningup/rl_intro.html).
  The clearest page on the vocabulary; the project is in maintenance mode, so treat the code as
  frozen.
- [Gymnasium](https://gymnasium.farama.org/) and [Stable-Baselines3](https://stable-baselines3.readthedocs.io/)
  (see its "RL Tips and Tricks" page). The environment standard and the algorithm library; its
  [algorithm table](https://stable-baselines3.readthedocs.io/en/master/guide/algos.html) says
  which algorithm accepts which kind of action.
- [CleanRL](https://docs.cleanrl.dev/). One file per algorithm, the shortest route from these notes
  to reading a real PPO or DQN implementation.
- [Williams, "Simple statistical gradient-following algorithms"](https://people.cs.umass.edu/~barto/courses/cs687/williams92simple.pdf)
  (*Machine Learning*, 1992; course copy). REINFORCE, the policy gradient used on the tank here.
- [Recht, "A Tour of Reinforcement Learning: The View from Continuous Control"](https://arxiv.org/abs/1806.09460)
  (*Annu. Rev. Control Robot. Auton. Syst.*, 2019; arXiv copy). Why a model and a controller
  usually beat model-free RL on control problems, with numbers.
- [Irpan, "Deep Reinforcement Learning Doesn't Work Yet"](https://www.alexirpan.com/2018/02/14/rl-hard.html)
  (2018). A practitioner's account of sample cost, reward design and seed failures.
- [Degrave et al., magnetic control of tokamak plasmas](https://www.nature.com/articles/s41586-021-04301-9)
  (*Nature*, 2022, open access). The strongest engineering result, and an example of what a good
  simulator makes possible.
- [Lazic et al., data center cooling using model-predictive control](https://proceedings.neurips.cc/paper/2018/hash/059fdcd96baeb75112f09fa1dcc740cc-Abstract.html)
  (NeurIPS 2018). The paper behind the cooling story, and a clear account of why historical
  control data was not enough.
- [Zhou, Li and Zare, optimizing chemical reactions with deep RL](https://pmc.ncbi.nlm.nih.gov/articles/PMC5746857/)
  (*ACS Central Science*, 2017, open access). Read it next to Lecture 15's Bayesian optimization.
- [Krakovna et al., specification gaming](https://deepmind.google/discover/blog/specification-gaming-the-flip-side-of-ai-ingenuity/)
  (DeepMind, 2020). The definition and a list of around 60 examples.
- [Henderson et al., "Deep Reinforcement Learning that Matters"](https://arxiv.org/abs/1709.06560)
  (AAAI 2018). Seeds, baselines and reporting.
- [Ouyang et al., InstructGPT](https://arxiv.org/abs/2203.02155) (2022). Where reinforcement
  learning sits in training a language model.
- Shin, Badgwell, Liu and Lee, ["Reinforcement learning: overview of recent progress and
  implications for process control"](https://doi.org/10.1016/j.compchemeng.2019.05.029)
  (*Computers & Chemical Engineering*, 2019), and Nian, Liu and Huang,
  ["A review on reinforcement learning: introduction and applications in industrial process
  control"](https://doi.org/10.1016/j.compchemeng.2020.106886) (2020). The process-control view;
  both are behind a paywall, available through the CMU library.

## Assignment

No assignment is released with this session. It is optional, and no assignment depends on it.

## Practice module

<a href="../../game/#/l20"><strong>Practice module for this session</strong></a>, for
participation credit.
