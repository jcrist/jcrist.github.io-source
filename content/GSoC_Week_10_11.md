Title: GSoC Week 10 & 11: Bogged down in details
Date: 2014-08-01 20:44
Category: GSoC
Tags: GSoC, sympy, pydy, dynamics
Slug: gsoc-week-10-11
Author: Jim Crist
Summary: Timelines are difficult, & code generation

I missed my post last week due to my research for grad school all going to hell
at the worst possible time :(. There wasn't much to report on last week, so I'm
not too perturbed. Turns out even with PRs done and tested, it still takes a
long time to get them merged and have everyone agree on them. Fortunately I
made up for it this week; as of now I am officially working on code generation!
This is behind schedule on my original timeline, but should have been expected,
as per [Hofstadter's law](http://en.wikipedia.org/wiki/Hofstadter%27s_law):

 > **Hofstadter's Law:** "It always takes longer than you expect, even when you
 > take into account Hofstadter's Law."

Things are moving ahead now, and I have some hope left that I can accomplish
(most of) everything I set out to do.

## Project Status:

I set out to accomplish a number of things this summer. Here's the status of
each project goal:

- **General Linearization Form:**

    Done!

- **Linearization methods for Kane's and Lagrange's Methods:**

    Done! Lagrange stuff got merged last week.

- **Documentation for the above:**

    Done? This PR is waiting for review, but I think it's good.

- **Pre-linearized solution methods:**

    Nixed from the plan due to lack of interest.

- **Code Generation:**

    In Progress...

I also accomplished a few other things, that I found necessary for my project:

- **Refactored `KanesMethod` and `LagrangesMethod`:**

    This resulted in more readable, pythonic code, and also a speed/memory
    improvement. PR for this is still awaiting review.

- **Faster `subs` function for `mechanics`:**

    My `msubs` implementation is several orders of magnitude faster than `subs`
    for the kinds of expressions seen in `mechanics` (even without the benefit
    of cacheing that `subs` has). This is in a PR awaiting review.

- **Soooo much work on the `nan` and `oo` issue:**

    Still not solved for *all* cases... :(

## TODO:

There are only 3 weeks left of GSoC! In my last remaining weeks, here's what I
plan to get done:

- **Get the Bicycle Example working:**

    After my work everything runs faster, results in smaller, more tractable
    expressions, and uses less memory. Except for the bicycle example. For some
    unknown reason I can not get this thing to result in anything except `nan`.
    This is a regress in performance (even though everything else runs better),
    and needs to be solved.

- **Code generation:**

    I've already got some stuff working, and it's really exciting. More on this
    below.

- **Get all my current stuff merged:**

    All that works needs to get into `Sympy`. As not everyone else is being paid
    to do this, it can take some time and effort to get things through the
    review process and into master, but I have hope that my remaining
    contributions will eventually make it in.

I think I can do it, but it'll be a stretch.

## Code Generation

Sympy currently contains some facilities for code generation, but they lack
support for the matrices that are necessary for working with dynamics problems.
I hope to remedy that, as well as to make general improvements to the entire
codegen module.

Code generation in sympy has three levels:

1. **Code Printers `ccode`, `fcode`, and the like**

    These are printers that know how to print *simple* sympy expressions using
    functionality and syntax found in that language. For example, `ccode` will
    print exponents using `pow`, which is found in the `math` library in C.
    These printers don't have any knowledge of functions, multiple statements,
    or header files. They simply print a single expression out on one line.

2. **The `codegen` submodule**

    This submodule contains facilities for representing generalized *routines*,
    and generating functions in various languages (currently C and FORTRAN)
    that can be compiled as a library without any changes. They know about 
    function and variable declarations, header files, library imports, and
    multi-line statements. However, they have no idea how to make this
    generated code work with python.

3. **Code wrapping, usually accessed through `autowrap`**

    This is where the functionality for *wrapping* the generated code lives.
    Using the functionality provided here, one can compile and wrap generated
    code, and then call it from python. The `autowrap` function is the main
    entry point, allowing for all 3 steps to be done in one call.

The first thing I wanted to fix was getting code generation to work with
matrices and matrix expressions. This turned out to be harder (and more
confusing) than I expected. There is currently support for a "matrix like"
object named `sympy.tensor.IndexedBase`, but I really don't understand the
purpose behind it. Reading through the code and examples though it seems to be
for representing indexed loop operations in a concise form. This unfortunately
has nothing to do with the indexed types (matrices) that I plan on
implementing.

I spent a long time reading through the code and playing around with it using
pdb trying to figure out the control flow in the codegen function, and am still
a little lost. Most of what's there seems to be for supporting the `Indexed`
operations.  After some time trying to bend them to work for matrices, I
changed plans and now am supporting `Matrix` and `MatrixExpr` types for matrix
operations only.  `Indexed` types can be used elsewhere, but they shouldn't be
used for representing matrices with expressions inside them.

I currently have this "working", but am not happy with it yet. The current
layout of the module made for some hacky work adding in matrix support. I plan
on doing some refactoring to make this implementation cleaner. Currently, on
my codegen branch the following is supported:

- **Generating C code for a matrix with expressions in each element:**

    Matrices are set as input-output type arguments, and are modified in place
    before being returned.

- **Passing in a `MatrixSymbol` as an argument:** 

    Here the plan is to use matrices to pass in a large number of arguments.
    You can think of this kind of like a vector. There's another symbolic
    vector type as well in Sympy (`DeferredVector`). I may end up supporting
    it, but I'm not really sure what it's for. In its current implementation,
    the following works:

        ::Python
        q = [q1, q2, q3, q4, q5]
        q_vec = MatrixSymbol('q', 5, 1)
        sub_dict = dict(zip(q, q_vec))
        # Replaces each q with elements from q_vec
        expr = msubs(expr, q_vec)
        # Generate a function that takes a numpy array (q) and returns expr
        # This works if expr is an expression, or a matrix
        func = autowrap(expr)

After I clean this up, I plan to add support for:

- **Common Subexpression Elimination (cse):**

    Even though modern compilers do this already, experimentation shows that
    the large expressions generated in `mechanics` benefit from generated code
    having cse performed. This will be implemented as a boolean kwarg (default
    False).  When True, sympy's `cse` function will be run on the expression,
    and the code for each subexpression will be generated, followed by the
    final expression.  I actually don't think this will be too difficult to
    implement, and should give some speed improvements on the compiled code (at
    the cost of slower generation).

- **A `ctypes` code-wrapper:**

    Currently the only code wrappers supported are `f2py` and `cython`, neither
    of which is in the standard library. While the wrappers generated with those
    functions may be more robust, a ctypes wrapper is also possible, with the
    added benefit that `ctypes` is in the standard lib.

- **Support for matrix expressions:**

    In an ideal world, I'd implement the excellent work done by Matthew
    Rocklin, discussed in [this video from SciPy
    2013](http://pyvideo.org/video/2028/matrix-expressions-and-blaslapack-scipy-2013-pr).
    The idea here is that we have some knowledge about each of the matrices
    involved in an *expression* (for example $A^{-1} B$). We may know that A is
    positive definite, or symmetric, or upper triangular, etc... For each case,
    there may be a faster inversion routine that we could take advantage of
    rather than using a one-size-fits-all inverse function. As I don't have time
    to implement support for all possible operations, and the many BLAS/LAPACK
    routines that support them, I'll focus just on the inverse, as it's commonly
    found in expressions in `mechanics`. The thought is, we should be able to
    run:

        ::Python
        func = autowrap(Inverse(M)*F)

    And have code generated that solves the expression in a fast manner, without
    having to symbolically find the inverse of `M` and combine it with `F` into
    one matrix beforehand.

Of course this is a wishlist, and it's unlikely all of this will be accomplished
in the next 3 weeks. Still, I plan to keep supporting `sympy` after my GSoC
ends, so if it's not done by then it will eventually get there.


---

### Other exciting news of the week:

I got accepted to the GSoC reunion at the end of October! As this is the 10th
annual GSoC, Google is throwing a big reunion shindig for past and present
students. As there are lots of us, only a few were chosen based on a lottery,
and I made it through! I'm very excited to meet other students that completed
the program, listen to some interesting talks, and see the GooglePlex. I also
bought my tickets to get there a day early so I have some time to explore the
bay area. Last time I was out there I was 14, and I didn't get to see much
of the area. If you also got accepted/live out and would be interested in
meeting up, let me know! I'll be in San Jose/San Francisco October 23-26.

