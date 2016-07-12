Title: Code Generation, and other things
Date: 2014-09-12 20:31
Category: sympy
Tags: sympy, ramblings
Slug: codegen-and-things
Author: Jim Crist
Summary: I gave a talk!

Long time, no post, but now I have news to share!

## `ufuncify` stuff

First, I just merged a PR to make SymPy's `ufuncify` create actual instances of
`numpy.ufunc`. This function takes in a tuple of arguments, and an expression,
and returns a binary function that will broadcast (apply the function to each
argument in turn) the arguments through the function, returning an array. An
example would be:

    ::Python
    from sympy import *
    from sympy.utilities.autowrap import ufuncify
    import numpy as np

    # Create an example expression
    a, b, c = symbols('a, b, c')
    expr = sin(a) + cos(b**2)*c

    # Create a binary (compiled) function that broadcasts it's arguments
    func = ufuncify((a, b, c), expr)
    func(np.arange(5), 2.0, 3.0)
<div class=md_output>

    array([-1.96093086, -1.11945988, -1.05163344, -1.81981085, -2.71773336])
</div>

Previously all broadcasting was done using hardcoded loops. These limited
arguments to:

- A single dimension array (only for the first argument)
- Scalars for the remaining arguments
- Floating point arguments (no type conversion)

Now, through the magic of [`numpy.ufunc`s](http://docs.scipy.org/doc/numpy/reference/ufuncs.html):

- *All* arguments can be n-dimensional arrays
- Type conversion happens implicitly

This makes this functionality *incredibly* more useful. My next step is to add
the ability for multiple outputs, and a custom wrapper so that matrix calculations
can be broadcast as well. This should help with repeated computation of matrices,
which is something [Jason](http://www.moorepants.info/blog/fast-matrix-eval.html)
needs for his work. This should be done (hopefully) by the end of next week.

## Code Generation Talk

I gave a talk yesterday on code generation in SymPy for our local Python User
Group. Discusses the why and how of the code generation tool chains we
developed, and gives a little demo. Slides are
[here](https://speakerdeck.com/jcrist/generating-fast-and-correct-code-with-sympy),
and the corresponding demo [here](https://github.com/jcrist/codegen_talk).

<script async class="speakerdeck-embed"
data-id="51ea3e201c2901324611222c32eaed08" data-ratio="1.77777777777778"
src="//speakerdeck.com/assets/embed.js"></script>

---

## Other things...

School recently started back up. In an effort to keep myself on task, I've started
doing AIOs:

- Accomplishments: What did I do in the last week
- Issues: Things that came up and interfered with accomplishing things over the
  last week
- Objectives: Things I'd like to get done in the upcoming week. Note that these
  should be doable in ~1 week.

I've been [hosting them on github](https://github.com/jcrist/AIOs) in an effort
to be open about my work, and update them every Friday. So far it seems to be a
good idea - at the end of each week I get a chance to reflect on what I did
that week, and what I plan to do over the next week. As a plus, my non-existant
internet readers get to hold me accountable to my to-do list :).
