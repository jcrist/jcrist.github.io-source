Title: GSoC Week 2: Started Work on Linearizer Class
Date: 2014-5-30 18:00
Category: GSoC
Tags: GSoC, sympy, pydy, dynamics
Slug: gsoc-week-2
Author: Jim Crist
Summary: Progress update, demonstration of functionality

This week I started work on implementing a general linearization method in 
`Sympy`. The current plan is to implement this in three parts:

### 1. **A `Linearizer` class**

This will hold the general form described by Luke and Gilbert's paper. The form
is:

\begin{aligned}
f_{c}(q, t) &= 0_{l \times 1} \\\\
f_{v}(q, u, t) &= 0_{m \times 1} \\\\
f_{a}(q, \dot{q}, u, \dot{u}, t) &= 0_{m \times 1} \\\\
f_{0}(q, \dot{q}, t) + f_{1}(q, u, t) &= 0_{n \times 1} \\\\
f_{2}(q, \dot{u}, t) + f_{3}(q, \dot{q}, u, r, t) &= 0_{(o-m) \times 1}
\end{aligned}

with

\begin{aligned}
q, \dot{q} & \in \mathbb{R}^n \\\\
u, \dot{u} & \in \mathbb{R}^o \\\\
r & \in \mathbb{R}^s 
\end{aligned}

Once in this general form, the algorithm devised by Luke and Gilbert is able to
linearize the system properly (not messing up due to constraints, as shown
[last week](http://jcrist.github.io/gsoc-week-1.html)). The resulting linearized
form is:

$$ M \begin{bmatrix} \delta \dot{q} \\\\ \delta\dot{u} \end{bmatrix} = 
A \begin{bmatrix} \delta q_{i} \\\\ \delta u_{i} \end{bmatrix} + B \begin{bmatrix}\delta r \end{bmatrix}$$

where $M$, $A$, and $B$ are matrices. A class method `linearize` is used to
perform this step.

### 2. **A `linearize` function**

This will take input systems of various forms (formed by `KanesMethod`,
`LagrangesMethod`, or ideally a general matrix of equations). The function
will then turn the system into the general form described above, create
an instance of `Linearizer`, call the `linearize` method, and return the
result.

To make this conversion easy and general, any class that implements a
`to_linearizer` method can be linearized. One has been written for
`KanesMethod` already. Originally I thought I could get equations formed
with Lagranges Method into this general form as well, but now I'm not sure.
The multipliers could be treated as dependent speeds (eliminating them from
the state vector), but for the linearization to be valid a trim point for
each multiplier will still need to be chosen. I'm going to think about this for
a while, and finish the remaining functionality for the `KanesMethod` class
first. If it turns out this can't be generalized for Lagrange's method, then a
seperate control flow path will need to be added.

### 3. **`linearize` class methods for `KanesMethod` and `LagrangesMethod`**

These will be nice wrappers for the linearize function, making the linearization
process as easy as creating the Method object, and then calling 
`Method.linearize()`.

## What's done so far

This week I implemented the beginnings of the `Linearizer` class. So far it can
only handle systems with *both* motion and configuration constraints. I plan on
finishing up the remaining control paths for just motion, just
configuration, and no constraint systems next week. For testing this
functionality, I used the rolling disk example used in Luke and Gilbert's paper.
With the current functionality, linearization works as:

    :::python
    # Equations for the disk are derived above, KM is a KanesMethod object
    >>> linearizer = KM.to_linearizer()
    >>> A, B = linearizer.linearize(eq_q, eq_u, eq_qd, eq_ud, A_and_B=True)

    # Evaluating in an upright configuration at critical speed:
    >>> upright_critical_speed = {q1d: 0, q2: 0, q3d: 1/sqrt(3), m: 1, r: 1, g: 1}

    #Calculating the critical speed eigenvalues, they should all be zero
    >>> A.subs(upright_critical_speed).eigenvals()
    {0: 8}

I also added a `to_linearizer` method to the `KanesMethod` class. This finds all
the needed information in the `KanesMethod` object, and returns a `Linearizer`
object. I'd say this is done as well, and is also tested in the
`test_linearize_rolling_disc` test.

Two other tests were also written, but not finished. They build off the example
I wrote up [last week](http://jcrist.github.io/gsoc-week-1.html) with a minimal 
and nonminimal pendulum system. I also have this same system worked out in
minimal and nonminimal coordinates using `LagrangesMethod`. Because it is so
quick to compute, and intuitive to know if it's correct or not I think this
will be an excellent way to test the functionality of the linearization
routines.

All of this work can be seen (and hopefully commented on, I need code review!) 
in [this pull request](https://github.com/jcrist/sympy/pull/1). As it's still
very much a work in progress, I made a pull request on my own master branch, 
so that others can review it before I submit it to Sympy proper.
