Title: GSoC Week 12 & 13: The End
Date: 2014-08-20 14:43
Category: GSoC
Tags: GSoC, sympy, pydy, dynamics
Slug: gsoc-week-12-13
Author: Jim Crist
Summary: Autowrap and wrapping up

The GSoC program officially ended this Monday, and so my work for SymPy has
concluded. I got *a lot* done in these last two weeks though. Here's what's
new. In order of completion:

### Complete overhaul of the codeprinting system

I wasn't happy with the way the codeprinters were done previously. There was a
lot of redundant code throughout `ccode`, `fcode` and `jscode` (the main three
printers).  They also had a lot of special case code in the `doprint` method
for handling multiline statements, which I felt could be better accomplished
using [the visitor pattern](http://en.wikipedia.org/wiki/Visitor_pattern) that
is used by all the other printers. The issue is that some nodes need to know if
they are part of a larger expression, or part of an assignment. For example, in
`C` `Piecewise` are printed as if statements if they contain an assignment, or
inline using the [ternary
operator](http://en.wikipedia.org/wiki/Ternary_operation) if they don't.

After some thought, this was solved by adding an `Assignment` node that
contains this information, and then dispatching to it in the printer just like
any other node. Less special case code, and allowed the base `CodePrinter`
class to contain a lot of the redundancies. For those implementing a new code
printer (perhaps for Octave?) all you'd need to do is add how to print certain
operators, and a dictionary of function translations.  Everything else *should*
just work. I may add little cleanups here and there, but I'm pretty happy with
the refactor.

### Code printers now support matrices

This was the original goal, but got put aside to do the previously described
refactor. The codeprinters now support matrices - both as inputs and outputs.
For example, the following now works:

    ::Python
    # Expressions inside a matrix
    x, y, z = symbols('x, y, z')
    mat = Matrix([x*y, Piecewise((2 + x, y>0), (y, True)), sin(z)])
    A = MatrixSymbol('A', 3, 1)
    print(ccode(mat, A))
<div class=md_output>

    A[0] = x*y;
    if (y > 0) {
       A[1] = x + 2;
    }
    else {
       A[1] = y;
    }
    A[2] = sin(z);
</div>

    ::Python
    # Matrix elements inside expressions
    expr = Piecewise((2*A[2, 0], x > 0), (A[2, 0], True)) + sin(A[1, 0]) + A[0, 0]
    print(ccode(expr))
<div class=md_output>

    ((x > 0) ? (
        2*A[2]
    )
    : (
        A[2]
    )) + sin(A[1]) + A[0]
</div>

    ::Python
    # Matrix elemnts in expressions inside a matrix
    q = MatrixSymbol('q', 5, 1)
    M = MatrixSymbol('M', 3, 3)
    m = Matrix([[sin(q[1,0]), 0, cos(q[2,0])],
        [q[1,0] + q[2,0], q[3, 0], 5],
        [2*q[4, 0]/q[1,0], sqrt(q[0,0]) + 4, 0]])
    print(ccode(m, M))
<div class=md_output>

    M[0] = sin(q[1]);
    M[1] = 0;
    M[2] = cos(q[2]);
    M[3] = q[1] + q[2];
    M[4] = q[3];
    M[5] = 5;
    M[6] = 2*q[4]*1.0/q[1];
    M[7] = 4 + sqrt(q[0]);
    M[8] = 0;
</div>

There even was a `Piecewise` inside a `Matrix` in there. As long as there is an
assignment between two compatible types (matrix -> matrix, scalar -> scalar),
the new codeprinters should print out valid expressions.

### `codegen` now supports matrices

This is more of a continuation of the above. The code generators have been
modified to recognize instances of `MatrixSymbol` as array variables and act
accordingly. There actually wasn't that much to change here to make this work.
The biggest change that happened is that *all* `C` functions that have a return
value (non `void` functions) allocate a local variable of the same type. This
is to cover a larger set of expressions, while still generating valid code. So
now, when performing codegen on "`sin(x)`" you won't get "`return sin(x)`",
you'll get:

    ::Python
    result = codegen(('sin_c', sin(x)), "C", "file", header=False)
    print(result)
<div class=md_output>

    double sin_c(double x) {

       double sin_c_result;
       sin_c_result = sin(x);
       return sin_c_result;

    }
</div>

This isn't as pretty, but handling return inside expressions is a tricky
problem, and this solves it without much work. Modern compilers should remove
the variable assignment if it's unnecessary, so there shouldn't be a resulting
speed loss in the code.

### `Cython` wrapper for `autowrap` now works

There was a code wrapper for `Cython` in the codebase, but I don't think it has
ever worked. It does now:) It can do everything `f2py` can do, and I plan on
adding more useful features. In it's current state it can:

- Handle both scalar and matrix input, input-output and output arguments
- Internally allocate output arguments
- Pull inferred variables (such as matrix dimensions) out of the function signature
- Create a multiple return value tuple

The last thing I want to do to make this *really* nice is to add support for
informative docstrings. Even so, this is already usable:

    ::Python
    x, y, z = symbols('x, y, z')
    mat = Matrix([x*y, Piecewise((2 + x, y>0), (y, True)), sin(z)])
    func = autowrap(mat, 'c', 'cython')
    func(1, 2, 3)
<div class=md_output>

    array([[ 2.        ],
           [ 3.        ],
           [ 0.14112001]])
</div>

For some reason the `Fortran`/`f2py` has around a 2 microseconds faster than
the `C`/`Cython` code. I think this has something to do with array allocations,
but I'm not sure. For larger expressions they're pretty equal, so this
shouldn't be that big of a deal. I still plan to look into code optimizations I
could make in the Cython wrapper.

## Project Status

Overall, I accomplished *most* of what I set out to do this summer. Some things
(pre-solution linearization) were nixed from the project due to changing goals.
Here's a short list of what was done:

1. General linearization methods added for both `KanesMethod` and `LagrangesMethod`.

2. Code cleanup and speedup for `KanesMethod` and `LagrangesMethod`.

3. Creation of `msubs` - a specialized `subs` function for mechanics
   expressions. This runs *significantly* faster than the default `subs`, while
   adding some niceities (selective simplification).

4. Complete overhaul of codeprinters. Fixed a lot of bugs.

5. Addition of support for matrices in code printers, code generators, and `autowrap`.

6. Overhaul of `Cython` codewrapper. It works now, and does some nice things to
   make the wrapped functions more pythonic.

7. Documentation for the above.

## The Future

I had an excellent summer working for SymPy, and I plan on continuing to
contribute. I have some code for discretization that I've been using for my
research that may be of interest to the mechanics group. I also want to get
common sub-expression elimination added to the code generators, as this kind of
optimization may result in speedups for the large expressions we see in
mechanics. My contributions will unfortunately be less frequent, as I need to
really focus on research and finishing my degree, but I still hope to help out.

I plan on writing another post in the next few days about the GSoC experience
as a whole, so I won't touch on that here. Let me just say thank you to Jason,
Luke, Oliver, Sachin, Tarun, Aaron, and all the other wonderful people that
have offered me guidance and support throughout the summer. You guys are
awesome.
