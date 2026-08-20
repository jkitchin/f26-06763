# Lecture 12: Architectures for engineering data: MLP, CNN, and sequence models

:::{admonition} Overview
:class: tip

- **Session** Lecture 12, Week 6
- **Arc** Machine learning and deep learning
- **Slides** <a href="../../slides/l12/">Deck for this session</a>
- **Demo** [`l12-cnn-rul.ipynb`](l12-cnn-rul.ipynb), a 1D-CNN for turbofan remaining-useful-life, against a tabular baseline
- **Assignment 6**, released at Lecture 11; this session's architectures are what it asks you to build
:::

## Why this matters

[Lecture 11](../l11/notes.md) built the machinery: tensors, autograd, a training loop, and a multilayer perceptron on tabular concrete data. It also delivered an uncomfortable result, that the MLP did not beat a gradient-boosted tree. This session is about the missing idea that a bare MLP throws away, which is **structure**.

An MLP treats its input as a flat vector of numbers with no relationships among them. That is the right picture for tabular data, where the columns are genuinely different quantities. It is the wrong picture for a great deal of engineering data, where the input has a shape the model should exploit. A temperature field from a simulation is a grid, and a pixel's neighbors matter. A vibration trace is a sequence, and a reading's recent past matters. Flatten either into a vector and you have told the model to relearn, from scratch and from limited data, a structure you already knew for free.

Matching the architecture to that structure is the whole subject. A vector goes to an MLP. A field or an image goes to a convolutional network. A sensor time series goes to a one-dimensional convolution or a recurrent network. The payoff is a model with fewer parameters that generalizes better, because it builds in an assumption that happens to be true. The honest counterweight, which this session takes as seriously as the promise, is that a deep architecture is not a default: on the turbofan data below, a quick 1D-CNN does not beat a well-built tabular baseline, and the reason it does not is as instructive as the cases where it does.

## Learning objectives

By the end of this session you should be able to:

- Match model architecture to the structure of the input (vector, field/image, sequence).
- Implement a 1D-CNN or RNN for sensor time series and a 2D-CNN for field/image data.
- Apply regularization and normalization appropriate to each architecture.

```{figure} figures/architecture_map.png
:alt: A table mapping input structure to architecture. A vector or tabular input (mix proportions, ambient readings) maps to an MLP. A field or image (a temperature or stress map from simulation) maps to a 2D-CNN. A sequence (multivariate sensor time series) maps to a 1D-CNN or RNN.
:width: 100%

The one decision this session is about. The structure of the input, not the size of the dataset or the fashion of the method, is what should pick the architecture.
```

## MLPs, and why scaling still matters

```{index} multilayer perceptron, activation function, dropout, batch normalization
```

The **multilayer perceptron** is the architecture for vector inputs, and Lecture 11 built one, so this session only adds the choices that shape it. Its two dials are **width** (units per layer) and **depth** (number of layers); more of either adds capacity and, past the point the data can constrain, adds overfitting. Between layers sits a nonlinear **activation**, and the modern default is **ReLU** (or its smoother cousin **GELU**), which trains faster than the older saturating sigmoids and tanh. Three regularizers keep a wide MLP honest: **dropout**, which randomly zeros a fraction of activations during training so the network cannot lean on any single unit; **weight decay**, which penalizes large weights; and **batch or layer normalization**, which rescales activations to keep the gradients well behaved.

One habit from earlier weeks does not go away because the model is now a neural network. Feature scaling still matters, because gradient descent on unscaled inputs takes tiny steps along the large-range features and overshoots the small-range ones. Lecture 11 measured the cost: unnormalized inputs make plain SGD produce a `nan` in the first epoch, while Adam quietly trains to a mediocre score and reports nothing wrong. Fold the scaler into the pipeline and fit it on training data only, exactly as in [Lecture 7](../l07/notes.md), because a neural network does not repeal the leakage rules from the Data Systems arc.

## CNNs for fields and images

```{index} convolution, convolutional network, kernel, stride, padding, receptive field, parameter sharing
```

A **convolutional network** is the architecture for data laid out on a grid: an image, or an engineering field such as a temperature, stress, or velocity map from a simulation. Its core operation is **convolution**, sliding a small **kernel** (a grid of weights, perhaps 3 by 3) across the input and computing a weighted sum at each position to produce a feature map. A few terms describe the sliding: the **stride** is how far the kernel moves between positions, **padding** adds a border so the output can keep the input's size, and **channels** are the stacked feature maps (three for a color image, one for a scalar field, many inside the network). **Pooling** then downsamples a feature map, taking the maximum or average over small regions, so deeper layers see a coarser, larger view.

:::{admonition} Definition: convolution and the receptive field
:class: tip

A **convolution** applies the same small kernel of weights at every position of the input, so a feature learned in one place is detected everywhere. The **receptive field** of a unit is, in the words of [Stanford's CS231n](https://cs231n.github.io/convolutional-networks/), "the spatial extent of this connectivity ... equivalently this is the filter size": the region of the input that can influence it. Stacking convolutions and pooling grows the receptive field, so deep units see wide context from small kernels.
:::

Two properties explain why a CNN needs far fewer parameters than an MLP for the same grid. Goodfellow, Bengio, and Courville put it that "convolution leverages three important ideas: sparse interactions, parameter sharing and equivariant representations." **Sparse interactions** come from the kernel being smaller than the input, so each output depends on a small patch rather than every input pixel. **Parameter sharing** means "using the same parameter for more than one function in a model": the same kernel weights are reused at every position, because a feature worth detecting in one corner of an image is worth detecting in the others. An MLP with a weight per input-output pair would have to learn each position's edge detector separately, from far more data. That reuse is why a CNN, not a bigger MLP, is the right tool for a stress field. The encoder-decoder and **U-Net** shapes that map a whole field to a whole field, the workhorse of simulation surrogates, build on exactly this and are developed in Week 7.

## Sequence models for sensor time series

```{index} 1D convolution, recurrent network, LSTM, temporal convolutional network
```

A sensor time series is a grid in one dimension, time, with a channel per sensor. Two architectures exploit that shape.

A **1D convolution** slides a kernel along time instead of across space. `torch.nn.Conv1d`, in the docs' words, "applies a 1D convolution over an input signal composed of several input planes," the planes here being the sensor channels. A 1D-CNN learns local temporal patterns (a spike, a ramp, a change in variance) and, stacked, assembles them into longer-range features, with the same parameter-sharing economy as its 2D cousin. A **recurrent network** instead walks the sequence step by step, carrying a hidden state that summarizes the past. Plain RNNs struggle to remember far back, so the practical variants are the **LSTM** and **GRU**, which add gates that let the state retain information over long spans; `torch.nn.LSTM` "applies a multi-layer long short-term memory (LSTM) RNN to an input sequence."

Which to reach for is a genuine engineering choice, and the answer has shifted. For years the reflex was an RNN for anything sequential, but Bai, Kolter, and Koltun (2018) found that "a simple convolutional architecture outperforms canonical recurrent networks such as LSTMs across a diverse range of tasks and datasets." A temporal CNN trains faster (its timesteps compute in parallel, where an RNN must go in order), handles short-to-medium windows well, and is the sensible default for the fixed-length sliding windows a sensor feed produces. Reach for an LSTM or a GRU when the dependence is genuinely long-range and variable, and for **attention and Transformers** when it is long-range and the interactions are complex, which is the machinery Week 8 onward is built on. Whatever the architecture, the windows must be normalized with statistics fit on training data only, and windowed so that no window straddles two units, which is the leakage lesson from [Lecture 8](../l08/notes.md) arriving in a new shape.

## Training a deep net well

```{index} learning-rate schedule, early stopping, gradient clipping, weight decay
```

An architecture that fits the data still has to be trained, and a handful of techniques separate a network that learns from one that stalls, oscillates, or overfits. The **learning-rate schedule** is the most consequential. A fixed learning rate is a compromise; lowering it over training lets the optimizer take large steps early and settle precisely late. Common schedules are **step** (drop by a factor every so many epochs), **cosine** (anneal smoothly to near zero), and **one-cycle**, from Smith's learning-rate practicum, which raises the rate to a maximum and back down within a single run.

:::{admonition} Definition: early stopping
:class: tip

**Early stopping** ends training when the validation loss stops improving, and keeps the checkpoint from the best epoch rather than the last. It is the cheapest regularizer: it prevents the many extra epochs in which a network memorizes the training set while its validation error climbs. The stopping decision uses the validation split, so the test set is still touched only once.
:::

Three more tools round out a stable recipe. **Gradient clipping** (`clip_grad_norm_`) caps the size of the gradient update, which prevents a single bad batch from blowing the weights up, and matters most for recurrent networks. **Weight decay** is the neural-network name for the same penalty on large weights an L2-regularized linear model uses. And **checkpointing** saves the best model to disk during training, so a crashed cloud instance or a diverging late epoch does not cost you the run.

Reading the loss curves is how you diagnose which problem you have. Training and validation loss both high and falling slowly is **underfitting**: too little capacity, or too low a learning rate. Training loss low while validation loss rises is **overfitting**: add regularization or stop earlier. A loss that oscillates or explodes is **bad optimization**: the learning rate is too high, or the inputs are unnormalized. Lecture 11's broken loops were all the third kind, and they are the ones a beginner most often mistakes for a modeling problem rather than a bug.

## Does the architecture earn its keep?

```{index} pair: case study; turbofan RUL 1D-CNN
```

The reference problem for a sensor sequence is **remaining useful life** (RUL): how many cycles until an engine fails, predicted from its sensor history. We use NASA's C-MAPSS FD001 turbofan set from [Lecture 8](../l08/notes.md), turning each engine's run into sliding windows of 30 cycles across 17 varying sensor and setting channels, and predicting a **piecewise-linear RUL** target, held constant at 125 cycles early in life and decreasing linearly thereafter, the convention introduced with this benchmark and standard ever since.

Two models compete on the same windows. A **1D-CNN** reads the raw sensor window. A gradient-boosting baseline reads hand-crafted summary features of each window (per-sensor mean, standard deviation, and last value). Both are evaluated with **GroupKFold by engine**, so no engine's windows appear in both training and validation, because the alternative silently inflates the score exactly as Lecture 8 showed.

```{figure} figures/cnn_vs_baseline.png
:alt: Left, a 1D-CNN training curve over epochs, train and held-out RUL RMSE both falling and leveling near 19 cycles. Right, a bar chart with error bars comparing the 1D-CNN at about 19.9 cycles RMSE and the gradient-boosting baseline at about 18.3, across four GroupKFold folds.
:width: 100%

The 1D-CNN reaches 19.9 plus or minus 2.0 cycles of RUL RMSE across four engine-grouped folds; the tabular baseline on window features reaches 18.3 plus or minus 1.0. The quick sequence model does not beat the strong baseline, and the gap sits inside the CNN's own fold-to-fold spread.
```

The result is the honest one, and it is more useful than a win would be. A convolutional model on the raw signal, the architecture that "should" fit a sensor sequence, lands a cycle or two behind a gradient-boosted tree on simple summary features, and the difference is within the noise. This echoes Lecture 11's tree-versus-net result and the broader finding of Grinsztajn and colleagues, who benchmarked 45 datasets and concluded that "tree-based models remain state-of-the-art on medium-sized data" of roughly ten thousand samples. The lesson is not that the CNN is bad; it is that a deep architecture earns its advantage from scale, from tuning it properly with the schedule and regularization above, and from data whose structure a hand-crafted feature cannot already capture. On a small, well-summarized benchmark, a strong classical baseline is the model to beat, and beating it is work.

:::{admonition} What a practitioner should take from this
:class: tip

Pick the architecture from the shape of the input: an MLP for a vector, a CNN for a field or image, a 1D-CNN or RNN for a sequence, and prefer a temporal CNN to an RNN for fixed windows unless the dependence is genuinely long-range. Fit scalers on training data only and window without crossing unit boundaries, because deep learning does not repeal the leakage rules. Train with a learning-rate schedule and early stopping, and read the loss curves to tell underfitting from overfitting from a bad learning rate. And always run a strong classical baseline: on engineering-scale tabular and windowed data, a deep net is not a default, and a model-family claim from a single run on a leaky split can evaporate when you close the leak and add seeds.
:::

## In-class demo

We frame turbofan RUL as a supervised problem on C-MAPSS FD001: sliding 30-cycle windows over the sensor channels, a piecewise-linear RUL target, and a `GroupKFold` by engine unit so no engine leaks across the split. We build a small 1D-CNN in PyTorch, train it with a learning-rate schedule and early stopping while logging per-epoch train and validation loss to MLflow, and checkpoint the best model as an artifact. Then we compare it against the Week-5 style tabular baseline on window features, on the same grouped folds. The moment to watch is the comparison: the sequence model does not automatically win, and the grouped split is what keeps that comparison honest rather than flattering. The runnable notebook is [`l12-cnn-rul.ipynb`](l12-cnn-rul.ipynb).

## Where this pushes back

The architecture-matching argument is sound, and it has limits worth stating.

### A matched architecture is a prior, not a guarantee

Choosing a CNN for a field builds in an assumption (locality and translation invariance) that is usually true and occasionally wrong. A global constraint, a boundary condition that couples distant points, or a physical symmetry the plain convolution does not know about, can make the built-in prior a liability. The architecture is a starting hypothesis about the data's structure, to be checked against a baseline, not a decision that ends the modeling.

### Depth needs data, and engineering datasets are often small

The parameter-sharing economy of a CNN reduces but does not remove deep learning's appetite for data. A thousand concrete mixes or a hundred engines is small by deep-learning standards, which is precisely why the tree keeps up. When the dataset is small, the honest move is often a strong classical model with good features, and the deep net earns its place as the data grows or as the raw signal carries structure no feature captures.

### The accelerator is not free, and bigger is not better

Lecture 11 measured a GPU running a small model 2.5 times slower than the CPU, because the fixed cost of each kernel launch dominates when there is little work to do. More layers, wider layers, and longer training are not free wins either; past the capacity the data can support they buy overfitting and cost time. Match the model size to the data, debug on CPU, and let the accelerator earn its place on a genuinely large run.

## Summary

The one idea of this session is to match the architecture to the structure of the input. A vector goes to an MLP, a field or image to a 2D-CNN, and a sensor sequence to a 1D-CNN or a recurrent network, because a convolution's parameter sharing and a recurrent state's memory build in assumptions that are true of that data and would otherwise have to be learned from scratch. For fixed sensor windows a temporal CNN is the sensible default over an RNN, faster to train and often as accurate. Training any of them well means a learning-rate schedule, early stopping on validation loss, gradient clipping, weight decay, and reading the loss curves to separate underfitting from overfitting from a bad optimizer, all tracked in MLflow. The turbofan comparison is the honest anchor: a quick 1D-CNN reaches about 19.9 cycles of RUL error against the baseline's 18.3, so the sequence model does not automatically win, and a grouped split by engine is what keeps the comparison from lying. Next week takes these building blocks toward surrogate models and the uncertainty that a real engineering prediction has to carry.

## Resources

- [PyTorch: Build the Neural Network](https://docs.pytorch.org/tutorials/beginner/basics/buildmodel_tutorial.html). Subclassing `nn.Module` and composing layers, the pattern every model here uses.
- [PyTorch `Conv2d`](https://docs.pytorch.org/docs/stable/generated/torch.nn.Conv2d.html) and [`Conv1d`](https://docs.pytorch.org/docs/stable/generated/torch.nn.Conv1d.html). The convolution APIs for fields and for sensor sequences, with the `in_channels`, `out_channels`, `kernel_size`, `stride`, `padding` parameters.
- [PyTorch `LSTM`](https://docs.pytorch.org/docs/stable/generated/torch.nn.LSTM.html). The recurrent option for long-range sequence dependence.
- [Goodfellow, Bengio, and Courville, *Deep Learning*, chapters 9 and 10](https://www.deeplearningbook.org/). Convolutional networks and sequence modeling, free online; the sparse-interactions and parameter-sharing argument is chapter 9.
- [Stanford CS231n: Convolutional Networks](https://cs231n.github.io/convolutional-networks/). The clearest short treatment of kernels, stride, padding, pooling, and the receptive field.
- [Bai, Kolter, and Koltun, "An Empirical Evaluation of Generic Convolutional and Recurrent Networks for Sequence Modeling" (arXiv:1803.01271)](https://arxiv.org/abs/1803.01271). Why a temporal CNN is a strong default over an RNN.
- [Grinsztajn, Oyallon, and Varoquaux, "Why do tree-based models still outperform deep learning on typical tabular data?" (NeurIPS 2022, arXiv:2207.08815)](https://arxiv.org/abs/2207.08815). The tabular-versus-deep-learning reality check behind the honest baseline.
- [Smith, "A disciplined approach to neural network hyper-parameters, Part 1" (arXiv:1803.09820)](https://arxiv.org/abs/1803.09820). The learning-rate range test and one-cycle schedule, developed in section 4.
- [NASA C-MAPSS turbofan dataset](https://ntrs.nasa.gov/citations/20090029214). Saxena et al. (2008) methodology; the FD001 subset is from the NASA Prognostics data repository, as in Lecture 8.

## Assignment

Assignment 6, "Train a PyTorch model on an engineering dataset," was released at [Lecture 11](../l11/notes.md) and is due about a week later. It asks you to build, train, and honestly evaluate a deep model (an MLP, a CNN, or a sequence model) on a real engineering dataset, using a GPU, with MLflow tracking and a comparison against a strong classical baseline. This session's architectures and training recipe are what it is built on. This is a pointer, not the rubric.
