# Lecture 20: Reinforcement learning, learning to act from rewards

:::{admonition} At a glance
:class: tip

- **Session** Lecture 20, Week 11 (optional)
- **Arc** Machine learning and deep learning
- **Slides** <a href="../../slides/l20/">Deck for this session</a>
- **Practice** <a href="../../game/#/l20">Practice module for this session</a>
- **Demo** [`l20-reinforcement-learning.ipynb`](l20-reinforcement-learning.ipynb), a bandit, tabular
  Q-learning on a tank against a tuned PID loop over ten seeds, and Q-learning against SARSA on
  cliff walking, each in seconds with NumPy alone
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

This session places reinforcement learning on the map of machine learning the course has drawn,
works three examples small enough to train in a browser, and ends on the question an engineer
actually faces: when is learning from reward worth that cost, and when is a model and a
controller the better tool.

## Learning objectives

By the end of this session you should be able to:

- Define reinforcement learning and its vocabulary: agent, environment, state, action,
  reward, policy, return, discount factor, value function, Q-function, episode, and
  exploration against exploitation (ε-greedy).
- Place reinforcement learning in the course's map of machine learning by the feedback the
  learner gets: a correct answer (supervised), samples of a distribution (generative), a score
  for one choice with no state (Bayesian optimization and bandits), or a score for a sequence of
  choices that change the system (reinforcement learning).
- Implement tabular Q-learning on tank level control and compare it with a tuned PID
  controller over several seeds.
- Explain why Q-learning and SARSA learn different paths on cliff walking, and what that says
  about exploring on a real plant.
- Say when reinforcement learning is the right tool and when a model with MPC, Bayesian
  optimization, or a tuned PID loop is, and read a published success claim for its baseline,
  seeds, sample count and simulator.

## Where reinforcement learning sits in machine learning

```{index} reinforcement learning, instructive feedback, evaluative feedback
```

```{index} see: RL; reinforcement learning
```

Machine learning methods differ most in what the learner is told. [Lecture 9](../l09/notes.md)
divided the field into three types by the data: supervised learning has labels, unsupervised
learning has none, and reinforcement learning "takes actions in an environment, receives state
updates and feedback, and learns which actions pay off." This session fills in the third type,
and the clearest way to do it is by the feedback.

:::{admonition} Definition: reinforcement learning
:class: tip
**Reinforcement learning** is learning which actions to take, in a system whose state the
actions change, from a numerical reward that scores the outcome instead of naming the correct
action.
:::

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
:alt: A table of five methods. Supervised learning sees x and the right answer y star and is told the right answer; a decision is one prediction. Generative models see samples and are told nothing but to match the data. Bayesian optimization and active learning choose x and see y, a score for that choice, one experiment at a time with no state. A bandit chooses an arm and sees a noisy score. Reinforcement learning acts and sees a reward and the next state; the score often arrives late and the action changes the state; a decision is a sequence.
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

## Bandits: the bridge from Bayesian optimization

```{index} multi-armed bandit, regret, epsilon-greedy
```

```{index} upper confidence bound, Thompson sampling, exploration-exploitation trade-off
```

Start with the simplest problem that has evaluative feedback and no state. You have five
candidate catalysts and a budget of 500 runs. Each run of catalyst $a$ gives a yield drawn from a
distribution whose mean $\mu_a$ you do not know. You want as much total yield as possible over
the 500 runs, which means using the best catalyst often while still trying the others enough to
know which one is best. This is the **multi-armed bandit**, named after a row of slot machines,
and it is chapter 2 of Sutton and Barto for a reason: it isolates exploration from everything
else.

The measure of a bandit strategy is **regret**, the yield lost to not knowing the answer:

$$
\text{regret}(T) = \sum_{t=1}^{T} \left(\mu^\ast - \mu_{a_t}\right),
$$

where $\mu^\ast$ is the best mean and $a_t$ the arm pulled at step $t$. A strategy that always
pulled the best arm would have zero regret. Every pull of a worse arm adds its gap.

The worked example uses means of 62, 70, 74, 66 and 58% yield for catalysts A to E, with a
run-to-run standard deviation of 8 points, so a single run of catalyst C can easily read lower
than a single run of B. Four strategies, 500 runs of 500 pulls each:

- **Greedy** tries each arm once, then always pulls the arm with the best average so far.
- **ε-greedy** does the same, except that with probability ε = 0.1 it pulls an arm at random.
- **Upper confidence bound** (UCB) pulls the arm with the largest
  $\hat\mu_a + c\sqrt{\ln t / n_a}$, where $n_a$ counts pulls of arm $a$.
- **Thompson sampling** keeps a Gaussian posterior for each mean, draws one sample from each,
  and pulls the arm whose sample is largest.

The last two are the acquisition functions of [Lecture 15](../l15/notes.md) with the surrogate
removed. UCB there was $\mu(x) + \kappa\,\sigma(x)$, the mean plus a multiple of the uncertainty;
here the uncertainty term shrinks as $1/\sqrt{n_a}$ because each arm's average tightens as it is
pulled. Thompson sampling is the same idea in both places: sample a plausible world and act as if
it were true.

```{figure} figures/bandit-regret.png
:alt: Left, cumulative regret over 500 pulls averaged over 500 runs. Epsilon-greedy ends highest near 880, greedy rises linearly to about 660, UCB with c equal to 2 reaches about 420, Thompson sampling about 270 and UCB with c equal to 8 about 210. Right, the share of the last 100 pulls spent on the best catalyst: greedy 0.73, epsilon-greedy 0.90, UCB c equal to 2 0.84, UCB c equal to 8 0.98, Thompson 0.98.
:width: 100%

Five catalysts, 500 pulls, 500 runs per strategy. Generated by
`lectures/l20/figures/make_figures.py`.
:::

Three results are worth reading closely. Greedy settles on a wrong catalyst in 27% of runs, because
one unlucky early yield from catalyst C convinces it that C is poor, and it never pulls C again
to find out otherwise. ε-greedy never gets stuck, but it ends with the highest regret of all, 884
points, because it keeps spending one pull in ten on random arms long after it knows the answer;
its regret grows linearly forever. UCB and Thompson sampling explore where the uncertainty is
and stop when it is resolved, which is why their curves flatten, and they end at 211 and 269
points.

The surprise is in UCB's constant. With $c = 2$, the value in Sutton and Barto's examples, UCB
locks onto a wrong arm in 16% of runs. Their rewards have a spread of about 1. These yields have
a spread of 8, so a bonus of 2 is small next to the noise and the method under-explores. Setting
$c$ to the noise standard deviation, $c = 8$, drops the stuck runs to under 1%. The constant has
the units of the reward, which is the same reason [Lecture 15](../l15/notes.md) wrote UCB as
$\kappa\,\sigma(x)$, letting the model's own uncertainty carry the units. A hyperparameter copied
from a textbook example carries that example's scale with it.

<div class="cw" data-widget="bandit" data-source="l20"></div>

Bayesian optimization is a bandit with a model. When the arms are continuous, temperatures or
compositions instead of five catalysts, you cannot pull each one even once, and a Gaussian process
connects the arms so that a measurement at 80 °C says something about 82 °C. What neither has is
state. The yield of the next run does not depend on which catalyst ran last. Add that dependence
and you have the full problem.

## The Markov decision process

```{index} Markov decision process, policy, return, discount factor
```

```{index} see: MDP; Markov decision process
```

The full problem has a standard form. An **agent** observes the **state** $s_t$ of an
**environment**, chooses an **action** $a_t$, and receives a **reward** $r_{t+1}$ and the next
state $s_{t+1}$. One run from a start to an end is an **episode**. In the tank, the state is the
level, the action is the inflow, the reward is minus the squared distance from the setpoint, and
an episode is 100 steps of half a time unit each.

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

The agent's behavior is its **policy**, $\pi(a \mid s)$, the probability of each action in each
state. Its goal is the **return**, the discounted sum of future rewards:

$$
G_t = r_{t+1} + \gamma\, r_{t+2} + \gamma^2 r_{t+3} + \dots = \sum_{k=0}^{\infty} \gamma^k r_{t+k+1}.
$$

The **discount factor** $\gamma$, between 0 and 1, sets how far ahead the agent looks. A reward
$k$ steps away counts $\gamma^k$ as much as one now, so the effective horizon is roughly
$1/(1-\gamma)$ steps. With the tank's $\gamma = 0.95$ that is 20 steps, or 10 time units, four times as long as
the tank takes to fill from 2 to 5 at full inflow. A $\gamma$ much smaller would make the agent
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
thing you can do from where it leaves you. Everything in the next section is a way of solving
this equation from samples, without knowing $p(s' \mid s, a)$.

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

## Q-learning on a tank

```{index} Q-learning, temporal-difference learning
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

**Q-learning** ([Watkins and Dayan, 1992](https://www.gatsby.ucl.ac.uk/~dayan/papers/cjch.pdf),
author's copy) keeps a table of $Q(s,a)$, here 20 states by 5 actions, 100 numbers, all starting
at zero. After every step it nudges one entry toward the Bellman target:

$$
Q(s,a) \leftarrow Q(s,a) + \alpha \left[\, r + \gamma \max_{a'} Q(s',a') - Q(s,a) \right].
$$

The bracket is the **temporal-difference (TD) error**: what the step suggested the value should
be, minus what the table said. The learning rate $\alpha = 0.2$ sets how far each sample moves
the entry. The agent chooses actions **ε-greedily** with ε = 0.2: usually the best action in its
table, one time in five a random one, because the table can only learn about actions that get
tried. Watkins and Dayan's convergence proof holds "so long as all actions are repeatedly sampled
in all states and the action-values are represented discretely", which makes exploration a
mathematical requirement as well as a practical one.

:::{admonition} Definition: Q-learning
:class: tip
**Q-learning** learns the value of each action in each state from experience, moving each
estimate toward the observed reward plus the discounted value of the best action in the next
state.
:::

The update uses the best next action, $\max_{a'}$, whatever action the agent will actually take
next. That makes Q-learning **off-policy**: it learns the value of acting greedily while behaving
ε-greedily. The distinction looks technical here and decides the outcome in the cliff example
below.

### A Q-learning update by hand

```{index} Q-table
```

The update is easier to trust once you have done it with numbers, so shrink the tank until the
table fits on a page. Give it three levels, low, ok and high, and two actions. Opening the valve
raises the level one step and shutting it lowers the level one step, with nothing past low or
high. Landing at ok earns +1, and opening costs 0.1, the same role as the tank's effort term.
The table $Q$ is then a 3 × 2 matrix, one row per state and one column per action, and it
starts at zero. Take $\alpha = 0.5$ and $\gamma = 0.9$.

The agent starts at low and opens the valve. It lands at ok, so $r = 1 - 0.1 = 0.9$. The next
state's row is still all zeros, so the target is $0.9 + 0.9 \times 0 = 0.9$, the TD error is
$0.9 - 0 = 0.9$, and the entry moves halfway: $Q(\text{low}, \text{open}) = 0.45$. One
transition changed one number. The agent then opens again from ok, overshoots to high, and pays
the 0.1 for opening, so $Q(\text{ok}, \text{open}) = 0.5 \times (-0.1) = -0.05$. From high it
shuts and lands at ok: $Q(\text{high}, \text{shut}) = 0.5 \times 1 = 0.5$.

The fourth update shows the Bellman recursion at work. From ok the agent shuts and drops to
low. The reward is 0, but the target is not: it is $0 + 0.9 \times \max(0, 0.45) = 0.405$,
because the first update taught the table that low is a good place to be when you can open
from there. So $Q(\text{ok}, \text{shut}) = 0.2025$, and the +1 that was earned by arriving at
ok from low has moved one step back, into the value of getting to low. When the agent opens
from low a second time, the target is $0.9 + 0.9 \times 0.2025 = 1.082$, and
$Q(\text{low}, \text{open})$ climbs from 0.45 to 0.766, because the target now includes the
value of what follows. A sixth step, opening from ok to high again, finds
$\max Q(\text{high}, \cdot) = 0.5$ and lifts $Q(\text{ok}, \text{open})$ from −0.05 to 0.15.

| After | Q(low, shut) | Q(low, open) | Q(ok, shut) | Q(ok, open) | Q(high, shut) | Q(high, open) |
|---|---|---|---|---|---|---|
| 6 scripted updates | 0 | 0.766 | 0.203 | 0.150 | 0.500 | 0 |
| 306 updates | 4.261 | 4.735 | 4.261 | 4.238 | 4.831 | 2.479 |
| $Q^\ast$, value iteration | 4.263 | 4.737 | 4.263 | 4.253 | 4.837 | 4.253 |

After 300 more ε-greedy steps, the table is within 0.02 of $Q^\ast$, computed directly from the
Bellman equation by value iteration, in every entry but one. The exception is
$Q(\text{high}, \text{open})$, which the agent tried twice in 306 updates, because a greedy
agent at high shuts. Its greedy actions were right after the third update and never changed.
This is the twenty-bin tank's behaviour in miniature: rarely visited entries are the last to be
right, and a table can act correctly long before every number in it is correct. Like the real
tank, no action holds the level at ok, so the best policy alternates, shutting from ok to low
and opening back. The figure steps through every update with its arithmetic.

<div class="cw" data-widget="q-hand" data-source="l20"></div>

```{figure} figures/qhand.png
:alt: Three 3 by 2 heat maps of Q values: after six scripted updates, after 306 updates, and Q star from value iteration
:width: 100%

The 3 × 2 Q matrix after the scripted episode, after 306 updates, and $Q^\ast$ from value
iteration. Bold marks the greedy action in each row. Computed in `figures/make_figures.py`.
```

### How the agent chooses an action

```{index} greedy policy
```

A trained table answers "what should I do?" by lookup. The agent finds the row for the current
state and takes the column with the largest value, $a = \arg\max_a Q(s, a)$. That is the same
final step as the classifier in [Lecture 10](../l10/notes.md), which scores every class and
reports the largest. The resemblance stops at what the scores mean and where they come from. A
classifier's scores are trained toward labels, the right class for each example. A Q-value is
an estimate of the return that follows the action, trained toward a target the agent built
from its own reward and its own table. Nobody ever says which inflow was right, and the agent
needs the numbers themselves as well as their order, because each target uses
$\max_{a'} Q(s', a')$ from the next state.

The argmax also explains why tabular Q-learning, and DQN after it, only handle actions that can
be listed. Five inflows are five columns. A valve that can sit anywhere between 0 and 2 has no
columns to compare, and finding the best action would itself be an optimization at every
step. Continuous actions need the policy to output the action directly, which is the subject
of the section on deep reinforcement learning below.

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

## Exploration has a cost: cliff walking

```{index} SARSA, on-policy, off-policy, cliff walking
```

On a real plant, exploration has a price. Sutton and Barto's Example 6.6 makes the cost visible
with a 4 × 12 grid. The agent starts at the bottom left and the goal is at the bottom right.
Every step costs −1, and the cells between them along the bottom edge are a cliff: stepping in
costs −100 and sends the agent back to the start.

Two algorithms learn it. Q-learning is the update above. **SARSA**, named for the quintuple
$(s, a, r, s', a')$ it uses, replaces $\max_{a'} Q(s',a')$ with $Q(s',a')$ for the action $a'$
the agent will actually take next:

$$
Q(s,a) \leftarrow Q(s,a) + \alpha \left[\, r + \gamma\, Q(s',a') - Q(s,a) \right].
$$

That makes SARSA **on-policy**: it learns the value of the policy it is following, random
exploratory moves included. Q-learning learns the value of the greedy policy it is not quite
following.

```{figure} figures/cliff.png
:alt: Left, return per episode during learning, averaged over 50 runs and smoothed. SARSA levels off near minus 26; Q-learning levels off near minus 49. Right, the 4 by 12 grid with the cliff along the bottom edge. Q-learning's greedy path runs along the row directly above the cliff in 13 steps; SARSA's path climbs to the top row, crosses, and comes down, 17 steps.
:width: 100%

Q-learning and SARSA with ε = 0.1, α = 0.5, 500 episodes, 50 runs. Generated by
`lectures/l20/figures/make_figures.py`.
:::

The two end up with different paths. Q-learning's greedy path runs along the edge of the cliff,
13 steps, the shortest route. SARSA's takes the long way across the top, 17 steps. While
learning, Q-learning earns an average of −49 per episode over the last 100 episodes and SARSA
−26, the same ordering as the book's figure. The book describes it this way: Q-learning "learns
values for the optimal policy, that which travels right along the edge of the cliff.
Unfortunately, this results in its occasionally falling off the cliff because of the ε-greedy
action selection." SARSA "takes the action selection into account and learns the longer but
safer path."

<div class="cw" data-widget="cliff" data-source="l20"></div>

Neither algorithm is wrong. Q-learning found the better policy for an agent that will stop
exploring. SARSA found the better policy for an agent that will keep making random moves. On a
plant, the question is which agent you are deploying, and whether random moves are ever
acceptable. A control system cannot step off a cliff ten percent of the time to find out how far
the edge is, and this is the main reason RL for real equipment is trained in a simulator.

The alternative is to learn from logged operating data, which is off-policy learning in its
purest form. It runs straight into the problem [Lecture 7](../l07/notes.md) called
closed-loop identification: data recorded while a controller was holding the plant steady
contains little information about what happens anywhere else. Google's 2018 data-centre
controller found exactly this when it tried to fit a model to a week of historical data from its
PID loops, as the case studies below describe.

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
appear in it. The problem has no state that the experiments change, which makes it a bandit in
the sense above. The RL framing works, and the comparison a reader most needs is missing.

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

**Exploration can be unsafe.** ε-greedy is not acceptable on equipment that can be damaged, as
cliff walking showed in miniature.

**A model often wins.** When you have a dynamic model, even an approximate one, model-based
control is usually far more sample-efficient. Recht's review of RL from the view of control
theory found that "the so-called 'model-free' methods popular in deep reinforcement learning are
considerably less effective in both theory and practice than simple model-based schemes when
applied to LQR," and that "Policy gradient, in particular requires thousands of times as many
samples as simple nominal control" ([Recht, 2019](https://arxiv.org/abs/1806.09460)). The same
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
| Choose the next experiment; outcomes do not change the system | Bayesian optimization (L15) or a bandit |
| A sequence of decisions, an accurate simulator, a controller hard to design by hand or redesigned often | reinforcement learning |
| No simulator, and exploring on the real system is unsafe | not reinforcement learning |

The PyCSE chapter lists the same conditions from the other side, including "When you have a good
mathematical model and can use optimization directly" and "When you can't simulate or the real
system is too expensive to experiment on."

## In-class demo

The notebook [`l20-reinforcement-learning.ipynb`](l20-reinforcement-learning.ipynb) runs the
examples with NumPy alone in about three minutes. It starts with the five-catalyst bandit and
all four strategies, then prints every number of the first six Q-learning updates on the
three-level tank and compares the result with $Q^\ast$. Then it trains tabular Q-learning on the
PyCSE tank, tunes a PID loop on the spot, and compares them over ten seeds and eight starts. It
changes the tank's reward twice and prints where the agent leaves the level, runs Q-learning
against SARSA on cliff walking, and trains the Gaussian policy on the tank with REINFORCE for
three seeds. An optional
last cell wraps the tank for Gymnasium and trains PPO if Stable-Baselines3 is installed. The
figures in these notes run the same code in the browser, so you can retrain each example with a
different seed.

## Summary

Reinforcement learning is the part of machine learning where the learner is scored and never
told the answer, and where its actions change the state it will face next. Bandits isolate
the first difficulty: on five catalysts, greedy choice got stuck on a wrong answer in a quarter
of runs, and UCB and Thompson sampling, the acquisition functions of Bayesian optimization
without the surrogate, kept regret lowest. The Markov decision process adds state and delayed
reward, and the Bellman equation explains how credit for a late reward travels back one step at
a time. Q-learning solves it from samples. On the PyCSE tank it beat a PID loop with untuned
gains from one start, and it lost to a tuned PID loop across eight starts and ten seeds. It had
two reasons to lose: its five inflows could not hold the setpoint, and half its seeds failed
from at least one start. A reward that said "keep it steady" produced a steady tank at the
wrong level. Cliff walking showed that the best policy depends on whether the agent keeps
exploring, which is why real equipment is trained in simulators. The successes are real, the
tokamak above all, and they share an accurate simulator and a controller that was hard to
design by hand. Without those, a model with MPC, a tuned PID loop, or Bayesian optimization is
usually the better tool. Every published claim deserves four questions: baseline, seeds,
samples and simulator.

## Resources

- [Sutton and Barto, *Reinforcement Learning: An Introduction*, 2nd ed.](http://incompleteideas.net/book/RLbook2020.pdf)
  (MIT Press, 2018, free from the authors). The standard text; chapters 1, 2 (bandits), 3 (MDPs)
  and 6 (TD learning, Q-learning, SARSA and Example 6.6) cover this session.
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
