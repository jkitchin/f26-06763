# Case study · Forecasting electricity demand

:::{admonition} At a glance
:class: tip
- **Field**: Energy systems and policy
- **Connects to**: [L7 · Features for time-series models](../lectures/l07/notes.md), [L8 · The machine learning workflow I, time series](../lectures/l08/notes.md), [L14 · Uncertainty quantification in machine learning](../lectures/l14/notes.md)
- **Primary source**: Hong, Pinson, Fan, Zareipour, Troccoli and Hyndman (2016), *International Journal of Forecasting* 32(3), 896 to 913
:::

## Why this matters

A grid operator has to match generation to demand every hour, and many of the decisions that make
that possible are taken days or weeks before the hour arrives. Which units to commit, how much
reserve to hold, and how much fuel to contract all depend on a forecast of the load. A single
number for each hour tells the operator what is most likely. It says nothing about how far the
load could swing on a hot afternoon, which is the case the reserve exists to cover.

A **probabilistic forecast** gives a distribution or a set of quantiles for each hour instead of
one value. The Global Energy Forecasting Competition 2014 (GEFCom2014) was built around this kind
of forecast. Its organizers
wrote that "most of the papers in the energy forecasting literature focus on point or
single-valued forecasts", and they built the competition around a scoring rule that rewards a
good distribution. The load track gives a clean, public, documented example of three ideas from
this course working together: features built from the clock and the weather, an honest
evaluation that runs forward in time, and an uncertainty that is checked against what happened.

## The setting

GEFCom2014 ran on the CrowdANALYTIX platform from August 15 to December 15, 2014, with four
tracks: electric load, electricity price, wind power and solar power. By the end it had 581
contestants from 61 countries, and the load track alone had 362. Hong and colleagues describe
the design and the results in the paper this page is built on.

The load track (GEFCom2014-L) asked contestants to forecast the quantiles of hourly load for a
US utility, one month ahead, on a rolling basis. The first data release contained 69 months of
hourly load (January 2005 to September 2010) and 117 months of hourly weather (January 2001 to
September 2010). Each week after that, the organizers released one more month of hourly load and
weather, which was the answer to the previous week's task. The weather came from 25 stations,
with no information about where they were. Contestants could also use the US federal holiday
calendar, which the paper lists in its Table 5.

The competition had a four-week trial period that did not count, followed by 12 scored weeks from
September 14 to December 6, 2014. Each week was a new forecast origin with a new month to predict.
This design is deliberate. The paper says rolling forecasting with weekly data releases was added
"to mimic real world forecasting processes".

The data are public. Tao Hong's blog post on the load-track data describes the package, with a
training file and a benchmark forecast for each of 15 tasks, and links a download for readers
without journal access. A student who wants to try this today on current data can also use the
US Energy Information Administration's [Hourly Electric Grid Monitor](https://www.eia.gov/electricity/gridmonitor/),
which publishes hourly demand by balancing authority, collected on Form EIA-930. The same form
collects each balancing authority's day-ahead demand forecast, so the operators' own forecasts can be
scored alongside yours.

## What happened

Every entry was scored with the **pinball loss**, also called the quantile score. For each hour
in the month, a team submitted the 1st through 99th percentiles of the load. For a quantile
forecast $q_a$ at level $\tau = a/100$ and an observed load $y$, the loss is

$$
L(q_a, y) =
\begin{cases}
(1 - \tau)\,(q_a - y) & \text{if } y < q_a \\
\tau\,(y - q_a) & \text{if } y \ge q_a
\end{cases}
$$

and the score is this loss averaged over all 99 quantiles and all hours. Lower is better. The
asymmetry is what makes it a quantile score. For the 90th percentile, a load that lands above the
forecast costs 0.9 per unit of miss, and one that lands below costs only 0.1, so the forecast that
minimizes the expected loss is the one exceeded 10% of the time. The organizers considered MAE, the
Kolmogorov-Smirnov statistic, the pinball loss and the continuous ranked probability score (CRPS).
They chose the pinball loss because the measure "needed to be a proper scoring rule", it was easy
to implement and explain, and it is "closely related to the CRPS anyway".

Teams were not ranked on raw pinball loss. Each week's entry was rated by "the percentage by which
it beats the benchmark", where the benchmarks "were generated using naïve models". The 12 weekly
ratings were combined with linearly increasing weights, so the last week counted 12 times as much
as the first. Sixteen teams beat the benchmark and submitted final reports. The winning team,
Tololo (P. Gaillard, Y. Goude and R. Nedellec, from France), had a rating of 50.8%, and the next four
had ratings of 49.8%, 48.9%, 48.5% and 46.2% (Table 3 of the paper).

Table 6 of the paper summarizes what the top five load teams did, and the methods differ more than
the scores do. Tololo used quantile regression and generalized additive models. Adada used
generalized additive models and combined forecasts with an exponentially weighted algorithm.
Jingrui Xie averaged point forecasts from several model families and simulated the residuals.
OxMath used conditional kernel density estimation and quantile regression. E.S. Mangalova used
Nadaraya-Watson kernel regression. The common ground lies outside the model itself. Three of the five
generated temperature scenarios: Tololo used 800 for short-term forecasting, Adada drew 1000 from
a temperature simulation model, and Xie used 10 scenarios built from 10 years of temperature
history. Three chose a subset of the 25 weather stations (four, three and 11 stations), and two
averaged all 25. Two used different methods for different parts of the month: Tololo used one
method for 1 to 48 hours ahead and another beyond 49 hours, and OxMath divided the horizon into
five periods.

## Why it happened

Temperature drives load, and the paper says so directly: "The temperature is a key factor driving
the load." The rest follows from one fact about the competition. When a team made its forecast for
next month, it did not have next month's temperature. That arrived a week later, with the answer.
So the load forecast inherited the uncertainty of a month of weather that nobody could forecast
well, and the paper notes that "the temperature is less predictable in the long term". Generating
temperature scenarios is the direct response. Each scenario is a plausible month of weather; in
Xie's entry, each was one past year of temperature history. Running the load model on each scenario
gives a spread of loads, and the quantiles of that spread are the probabilistic forecast.

The other standard inputs come from the calendar, because people use electricity on a schedule.
The standard linear benchmark in this literature, which Xie's dissertation calls Tao's Vanilla
Benchmark and which GEFCom2012 used as its load benchmark, makes this explicit. It regresses load on
a trend term (gross state product in Xie's version), month, weekday, hour, and a weekday-by-hour
interaction. It adds a cubic polynomial in the current hour's temperature and interacts that
polynomial with month and hour. The interactions let the effect of one degree of temperature differ
by month and by hour of the day. Xie's dissertation also describes later refinements. A **recency
effect** adds the temperatures of preceding hours. A weekend effect groups days that behave alike.
A holiday effect treats holidays as weekend days, since the history holds few examples of each one.

Why the split between short and long horizons? For the first day or two, the recent load and the
recent weather still carry information, so a short-term model can beat a weather-scenario model.
After that, the past month says little about the specific hours ahead, and the forecast falls back
on calendar effects and the range of temperatures typical for the season. The competition designers built this in on
purpose: they chose a one-month horizon so that "there was some room for the contestants to develop
short-term load forecasting models to improve the scores for forecasts a few days ahead".

## Connections to the lectures

The features in the winning models are the ones [L7](../lectures/l07/notes.md) builds. The recency
effect is a set of lagged temperature columns, the same `shift` the section on multiple lags and the
regression vector uses to widen the design matrix. L7's warning there carries over: lags of a smooth
signal such as hourly temperature are nearly copies of each other, so their individual coefficients
will not mean much. The section on data leakage in L7 explains why scenarios were necessary.
Next month's measured temperature is a column holding information from after the forecast time.
A model fed the true temperature for the forecast month would score far better in a backtest than
it ever could in use, which is target leakage in its plainest form.

[L8](../lectures/l08/notes.md) makes the same point in its section on the forecast horizon. It says
a load forecaster can use tomorrow's weather only because a weather forecast for tomorrow exists
today. At a one-month horizon no useful weather forecast exists, so scenarios stand in for it.
GEFCom2014 also shows L8's section on evaluating on time at full scale. The 12 weekly tasks are a
rolling-origin evaluation: each task trains on everything released so far and is scored on a month
that nobody had seen. The rating against a naïve benchmark is a skill score in the sense of L8's
section on baselines and skill. Very different model families finished close together, and the gap between first and fifth (50.8% against
46.2%) is small next to the gap between any of them and the benchmark. Tololo's split at 48 hours
is close in spirit to L8's direct strategy, with a separate model for a separate range of horizons.

[L14](../lectures/l14/notes.md) supplies the vocabulary for the scoring. Its section on calibration
defines a calibrated quantile forecast as one where the observed value falls below the predicted
$p$-quantile a fraction $p$ of the time. Submitting 99 quantiles is a way of stating that whole
distribution. The pinball loss belongs to the family L14 introduces under proper scoring rules, and
the GEFCom organizers chose it for that property. Averaged over all quantiles, it rewards sharpness
subject to calibration. A team cannot gain by widening every interval, the way L14's climatological
forecaster stays calibrated and useless, and it cannot gain by narrowing intervals the data do not
support. The pinball loss is also the loss minimized by quantile regression, the method Tololo
used, which is the same quantile regression that conformalized quantile regression in L14 builds on.

:::{admonition} What a practitioner should take from this
:class: note
- Before building the table, list which inputs will be known at forecast time. If a driver such as
  temperature will not be, either forecast it or simulate it, and never train on its measured value.
- Score probabilistic forecasts with a proper scoring rule such as the pinball loss or CRPS, and
  report coverage at a few quantile levels next to it, so a reader can see calibration directly.
- Start from a calendar-and-temperature regression like the Vanilla benchmark. It is cheap and
  explainable to an operator. The top five GEFCom2014 load teams had ratings of 46 to 51% against
  a naïve benchmark, a realistic sense of what a strong model adds.
- Expect the best model to depend on the horizon. Measure error separately for the first two days
  and for the rest, and be willing to use two models.
- Evaluate with rolling origins, one forecast period at a time, the way the competition did.
:::

## Sources

- Hong, T., Pinson, P., Fan, S., Zareipour, H., Troccoli, A. and Hyndman, R. J. (2016). [Probabilistic energy forecasting: Global Energy Forecasting Competition 2014 and beyond](https://robjhyndman.com/papers/gefcom2014.pdf). *International Journal of Forecasting* 32(3), 896 to 913, [doi:10.1016/j.ijforecast.2016.02.001](https://doi.org/10.1016/j.ijforecast.2016.02.001). The primary source for every competition figure on this page; the link is a copy of the published article hosted on co-author Rob Hyndman's site. Section 3.2 has the scoring rule and Table 6 the methods.
- Xie, J. (2016). [Probabilistic electric load forecasting](https://ninercommons.charlotte.edu/record/760/files/XIE_uncc_0694D_11220.pdf). PhD dissertation, University of North Carolina at Charlotte. Written by the third-place load team, open access, and the clearest description found of the Vanilla benchmark, the recency effect and the pinball loss.
- Hong, T. (2017). [GEFCom2014 load forecasting data](https://blog.drhongtao.com/2017/03/gefcom2014-load-forecasting-data.html). The competition chair's blog post describing the released data package task by task, with a download link that does not need journal access.
- Gaillard, P., Goude, Y. and Nedellec, R. (2016). Additive models and robust aggregation for GEFCom2014 probabilistic electric load and electricity price forecasting. *International Journal of Forecasting* 32(3), 1038 to 1050, [doi:10.1016/j.ijforecast.2015.12.001](https://doi.org/10.1016/j.ijforecast.2015.12.001). The winning load team's own account; paywalled, and no open copy was found.
- Hong, T. and Fan, S. (2016). Probabilistic electric load forecasting: A tutorial review. *International Journal of Forecasting* 32(3), 914 to 938, [doi:10.1016/j.ijforecast.2015.11.011](https://doi.org/10.1016/j.ijforecast.2015.11.011). The standard review of the field, recommended to GEFCom2014 contestants; paywalled.
- US Energy Information Administration. [Hourly Electric Grid Monitor](https://www.eia.gov/electricity/gridmonitor/) and the [Form EIA-930 instructions](https://www.eia.gov/survey/form/eia_930/instructions.pdf). Current hourly demand by balancing authority, with the operators' day-ahead demand forecasts, for anyone who wants to build and score a load forecast on live data.
