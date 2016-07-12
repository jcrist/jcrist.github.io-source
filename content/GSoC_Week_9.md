Title: GSoC Week 9: Docs!
Date: 2014-7-18 15:00
Category: GSoC
Tags: GSoC, sympy, pydy, dynamics
Slug: gsoc-week-9
Author: Jim Crist
Summary: Writing documentation is hard...

This week I spent time on all sorts of little things:

- Finished up the refactoring of `KanesMethod`
- Little fixes to [my current PR](https://github.com/sympy/sympy/pull/7681). Just
  waiting on my mentors to review this, I want to get it merged soon-ish.
- Documentation.

Writing documentation is the worst[^1]. After taking time to implement all sorts
of new interesting things, the last thing I want to do is go back and write about
them in detail. Which is why it's so important to do early on. *Good*
documentation needs to accomplish three things:

1. Provide motivation for *why* your software is necessary/better/useful.
2. Describe the user interface, showing *how* to use each function or class.
3. Provide real world *examples* showing how to tie everything together.

Python's documentation is interesting in that there are varying ways to do it.
Some of Sympy's documentation is just a nicely rendered form of the docstrings
for all the methods. Other modules have a more prose-y explanation of their
functionality. `mechanics` is one of those modules.

In my opinion the prose documentation approach is the better way.
Having good docstrings is important, but they aren't the end-all of
documentation[^2]. Of course, if I have a question the first thing I'm going to
do is read the docstrings (IPython makes this trivially easy). Only if I still
have questions afterwards will I turn to the online documentation. However, it'd
be extremely off-putting if the online documentation was just the docstrings
again.

With the various changes I've made so far I needed to:

1. Update the `LagrangesMethod` documentation to reflect the interface change.
2. Create a documentation page all about the linearization methods.
3. Update all the examples to reflect the new functionality.

All of these are "done". I still need to go through and proofread, but overall
I'd say that the current state of the documentation is acceptable. I would like
to take some time to reorganize the layout of the whole `mechanics` documentation
at some point. The current layout isn't the easiest to navigate for what you're
looking for.

With this out of the way, the linearization portion of my project is tentatively
done. I say tentatively because I'm still waiting on my PRs to get merged, and 
am also still playing around with solving [the `nan` issue](http://jcrist.github.io/gsoc-week-8.html)
that I've been writing about these last couple weeks.

With that done, I hope to move on to code generation. I've read the current code
generation code and documentation, as well as [this pydy wiki page](https://github.com/pydy/pydy/wiki/codegen-planning)
on Jason's ideas about code generation. I'm still a little iffy about the intention
of this functionality, so I'm waiting until we can all meet to discuss what needs
to be done. That was supposed to have happened this week, but fell through.
Hopefully we can set some time aside next week, and I can finally get to work
on it.


[^1]: Not actually the worst.
[^2]: [This article](http://stevelosh.com/blog/2013/09/teach-dont-tell/) by Steve
      Losh is a really good read on this.
