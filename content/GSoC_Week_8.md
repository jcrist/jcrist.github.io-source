Title: GSoC Week 8: Try, try, try again...
Date: 2014-7-11 17:00
Category: GSoC
Tags: GSoC, sympy, pydy, dynamics
Slug: gsoc-week-8
Author: Jim Crist
Summary: Trying out several potential solutions to the `nan` problem.

I'm still struggling to solve the `nan` and `oo` issue I've discussed in my
post [a couple weeks ago](http://jcrist.github.io/gsoc-week-6.html).
[Last week](http://jcrist.github.io/gsoc-week-7.html) I showed off a custom
written subs function for use inside `sympy.physics.mechanics` that helped with
speed considerably, and *attempted* to solve the `nan` problem. This worked
great for small-medium expressions, but failed on large ones. Or did it? I'm not
sure anymore.

[This pull request](https://github.com/sympy/sympy/pull/7464) brought up something
that I had witnessed, but never really thought about as a potential source of my
issues. To summarize, Sympy's current (hopefully soon to be old) caching system
never clears. Ever. For interactive work, or short running sessions this is fine.
However, for the huge expressions generated in `mechanics`, this can be a source
of memory issues, as the cache grows to hold all sub-expressions that were cached.

It turns out that `simplify` is one of those functions that is cached. This may
explain why when I tried to use `msubs` with `smart_subs=True` (which crawls the
expression tree and does selective simplification) this resulted in *all* of my
RAM being used up (4 GB!!!). I haven't had a chance to pull in this PR into my
repo and test it out, but it sounds like it should fix the problem. Instead of
growing infinitely, the cache uses a [least recently used (LRU)](http:
//en.wikipedia.org/wiki/Cache_algorithms#Least_Recently_Used) algorithm to
determine what stays and what is removed. The cache size can be set by the user,
so those that prefer speed over memory use can still cache everything. Per his
benchmarks it seems to be only 10% slower, which shouldn't be much of a problem.
Overall, I'm really psyched to start using this. Perhaps with this the `smart_subs`
I wrote up will work, even if it takes a while. If not, I'm kind-of out of ideas.

I spent some time this week trying out a few other ways of solving this problem.
So far none of them have worked.

### 1. Using `cse`, and applying simplify selectively to the sub-expressions.

The basic idea here was to apply `cse` on the expression, and then evaluate
each sub-expression. If it evaluated to `nan`, simplify it, then evaluate it
again.

This seemed like a good idea at first, but upon closer examination it
falls apart. The issue is that the expressions that could cancel/simplify out
are often broken into *separate sub-expressions*. This means that they are
evaluated numerically separately, and only once combined will they result in
a `nan`, at which point they can't be simplified anyway.

### 2. Taking the limit of the bad sub-expressions.

This was another idea that seemed good until I tried it. Similar to the `smart_subs`
I talked about [last week](http://jcrist.github.io/gsoc-week-7.html), except this
time it's taking the limit of the bad sub-expressions as they approach the operating
point. The thought being that it may be computationaly cheaper to find the limit
than to apply `simplify` and then evaluate.

There were several problems iwth this design. The first being that `Sympy` has no
functionality for finding multivariable limits. These can't be calculated
iteratively either (by that I mean find the limit for x, then the limit for y, then
the limit for z, etc...), as the part that could "simplify out" could already be
gone.

The second, and more serious issue, is that there was no way to tell if the limit
at that point was equal to the value the expression should actually evaluate too, or if it
is just the value of the *limit at that point*. For example:

    :::Python
    >>> expr = (a - 1)/(a**2 - 1)
    >>> op_point = {a: 1}
    >>> expr.subs(op_point)
    nan
    >>> limit(expr, a, 1, '+')
    1/2
    >>> limit(expr, a, 1, '-')
    1/2


Using the method described above, it would seem that the expression should just
evaluate to `1/2`. However, if you actually plot this expression, you'll find
that there is a discontinuity at `a = 1`. From either side it approaches 1/2,
but at 1 it is actually `nan`.

### 3. Numerical perturbation about the setpoint to find the limit of the bad sub-expressions.

The idea here was to calculate the limit of the sub-expressions through numerical
evaluation and perturbation. This fails for all the reasons described above, as
well as the fact that Sympy is a symbolic computation library, and we should be
able to do this symbolically.

-------

Unfortunately those were all the ideas I had to solve this problem. If the algorithm described
last week doesn't end up working using the new cacheing system, I'm kind of stumped.
Back on [the struggle bus](http://www.seas.upenn.edu/~terfan/strugglebus/pennapps2013f/)...

-------

## Meanwhile...

As another *potential* solution, I've set about refactoring the `KanesMethod` class
in the hope that I'll find some way of generating expressions that are smaller
than they currently are. The first step was rewriting to make it readable, more
modular, and remove the dead code that had built up over the years. This is done.
In it's current state it passes all tests, and runs them in half the time that it
had before!!! Still no major reduction in expression size, but I'll hopefully find
some magical place in the code that could be made more efficient. We'll see.

I'm also working on the documentation for the linearization stuff that's already
done, as well as waiting on someone to finally review my
[PR for LagrangesMethod support](https://github.com/sympy/sympy/pull/7681). I hope to
get that merged soon so that I can get started on the code generation portion of this
project.




