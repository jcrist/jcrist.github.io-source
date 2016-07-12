Title: GSoC Week 6: Just the little things
Date: 2014-6-27 21:21
Category: GSoC
Tags: GSoC, sympy, pydy, dynamics
Slug: gsoc-week-6
Author: Jim Crist
Summary: Little fixes, and a dillemma of sorts

I was rather busy with my research this week, so no time for a long-winded
post like [some of my](http://jcrist.github.io/gsoc-week-1.html) 
[previous](http://jcrist.github.io/gsoc-week-4.html) 
[updates](http://jcrist.github.io/gsoc-week-5.html). There's not
much interesting to say anyway. This week was mostly spent on little fixes to
get my current [pull request](https://github.com/sympy/sympy/pull/7581) merged.

Topping the list of things that are better than they were last week is speed.
The profiling I did [last week](http://jcrist.github.io/gsoc-week-5.html)
showed that the current function `sympy.physics.mechanics` uses to solve a
system of linear equations (`_mat_inv_mul`) is *sloooooooooow*. The underlying 
reason is because `subs` is slow - more on that later. I spent some time
swapping out all forms of solving ($A x = B$) for `LUsolve`, the clear winner
of last weeks benchmarks. This resulted in a 10x speedup of the formulation of
equations for the [bicycle model example](http://docs.sympy.org/dev/modules/
physics/mechanics/bicycle_example.html). 

This bicycle example has become the bane of my existence for the last couple
weeks. It's a super slow test that I'd never actual gotten to run before. But
with the speed improvements made, it actual finishes in a reasonable time.
Except it still doesn't work. I'm able to run all the way up to

    :::Python
    M, A, B = KM.linearize()

But when I go to sub in values for symbols in these matrices, things get hairy.
There are two issues:

### Issue 1: Get `nan` when not simplified

`M.subs(val_dict)` results in `nan` and `oo` upon after `subs`. But doesn't
if it's simplified before the subs. An example of this behavior would be:

    :::Python
    >>> M = sin(q1)/tan(q1)
    >>> M.subs({q1: 0}
    nan

Note that if this is simplified, this results in something completely different:

    :::Python
    >>> M = sin(q1)/tan(q1)
    >>> M = M.trigsimp()
    >>> M
    cos(q1)
    >>> M.subs({q1: 0})
    1

However, for the bicycle case M has *over 19 thousand operations*. This doesn't
simplify quickly. Also, by default we don't simplify before `subs` in
`Linearizer` (you can opt in to simplify, but it's done right before the return,
so it won't affect the subbed result at all). Right now I'm looking through
ways to make the resulting expressions smaller after the formulation, as this 
will result in speedups for *all* operations. This could be extremely helpful
for issue 2...

### Issue 2: `subs` is slow

because `A` has *over 38 million operations*!!! In this case `subs` doesn't even
return. Ever. I left it running on my computer for 4 hours and came back and it
was still whirring along, fans on high, eating up all my ram. No idea how to
solve this. One possible solution is [csympy](https://github.com/sympy/csympy),
a fast core written in C++. Once this matures, `subs`, `trigsimp`, and other
time consuming operations used heavily in `sympy.physics.mechanics` could rely
on the equivalent, faster, C++ versions. I filed an issue with an example
expression generated from the bicycle example (this one only had 147,841
operations, not nearly as bad). Hopefully Ondrej and the team can use this
as a benchmark problem to help improve `subs` in csympy.


If you have thoughts on how to overcome these issues, **please let me know**.
I'm kind of stumped right now.

## The Good News

I didn't want to end this post on a bad note, so I'll close with the remainder
of the things I did last week that actually worked:

1. Improved documentation! Docstrings that are worth reading, and a start on the
sphinx documentation.

2. Added a deprecation warning for `KanesMethod.linearize` to warn people about
the method change.

3. Major interface changes. Now all operating points are specified as a single
dictionary, or an iterable of dictionaries. This is to aid in consistency across
different system implementations. Referring to a dictionary as `u_op` in 
`LagrangesMethod` doesn't really make any sense, as Lagrange's method only uses
$q$, $\dot{q}$, and $\ddot{q}$. Also added a kwarg to make simplification of the
results optional.

4. Added a method to the `LagrangesMethod` class to calculate the value of the
multipliers at different points. This is useful for multiple reasons. The
multipliers have meaning, so knowing what the solution is symbolically is nice
for calculating the constraint forces. Also, when linearizing with Lagrange's
method, the multipliers have operating points as well, and these need to be
calculated based on the operating point for the other states ($q$, $\dot{q}$,
etc...). Now a user can go:


        :::Python
        op_point = dict_or_iterable_of_dicts
        lam_op = LM.solve_multipliers(op_point)
        op_point.append(lam_op)     # Or op_point.update if op_point is a dict, not a list of dicts
        M, A, B = LM.linearize(q_ind=q_ind, qd_ind=qd_ind, op_point=op_point)


Hopefully in the next week I can get my PR merged, so the Lagrange stuff can
finally be submitted.
