Smaller Docker images with Conda
################################

:date: 2019-06-03 14:30
:category: conda
:tags: conda, docker
:slug: conda-docker-tips
:author: Jim Crist
:summary: Tips for reducing the size of docker images that use Conda


Summary
-------

We provide a few tips for reducing the size of docker images that use Conda,
reducing an example docker image to 15% of its original size.


Introduction
------------

Conda_ is a useful tool for managing application dependencies. When combined
with Docker_ for deployment you can have a nice workflow for reproducible
application environments.

If you're not careful though, you can end up with extremely large Docker
images. Larger images increase disk usage, are slower to upload/download, and
have an increased attack surface. While image size isn't always important, I
wanted to see how small an image I could reasonably create running Dask_ (a
Conda_ backed application).

The end result is a set of docker images for running Dask_, which can be found
here_. Below we'll walk through all the steps involved in reducing the image
size.


Step 0: Initial Working Image (1.69 GB)
---------------------------------------

We'll be working through reducing the size of an image for running the Dask
Scheduler/Workers (a simplified version of those found in the official
`dask-docker images`_. The ``Dockerfile`` is as follows:

.. code-block:: docker

    FROM continuumio/miniconda3:4.6.14

    RUN conda install --yes \
        dask==1.2.2 \
        numpy==1.16.3 \
        pandas==0.24.2 \
        tini==0.18.0

    ENTRYPOINT ["tini", "-g", "--"]

It installs a few dependencies, and sets tini_ as the entrypoint. Building and
testing that it works:

.. code-block:: shell

    # Build the image
    $ docker build . -t myimage
    ...

    # Start a dask scheduler
    $ docker run myimage dask-scheduler
    distributed.scheduler - INFO - -----------------------------------------------
    distributed.scheduler - INFO - Clear task state
    distributed.scheduler - INFO -   Scheduler at:     tcp://172.17.0.2:8786
    distributed.scheduler - INFO -       bokeh at:                     :8787
    distributed.scheduler - INFO - Local Directory:    /tmp/scheduler-wcgj6uqw
    distributed.scheduler - INFO - -----------------------------------------------

Everything works as expected, hooray! Unfortunately our image size is a bit
larger than we'd like:

.. code-block:: shell

    $ docker image ls myimage
    REPOSITORY          TAG                 IMAGE ID            CREATED             SIZE
    myimage             latest              8856981797ab        2 minutes ago       1.69GB

Our naive image is 1.69 GB, just for running the dask scheduler! Surely we can
do better than that!


Step 1: Don't use MKL (729 MB)
------------------------------

When using the ``defaults`` Conda channel, ``mkl`` is installed as the BLAS
library. While fast, the binaries included are rather large:

.. code-block:: shell

    $ du -ch /opt/conda/lib/libmkl_* | grep total
    746M    total

The easiest fix for this is to use ``openblas`` instead of ``mkl``, which can
be done by adding ``nomkl`` as a dependency. Users using the Conda-Forge_
channel will get ``openblas`` by default and won't need the ``nomkl``
dependency.

.. code-block:: docker

    FROM continuumio/miniconda3:4.6.14

    RUN conda install --yes \
        nomkl \
        dask==1.2.2 \
        numpy==1.16.3 \
        pandas==0.24.2 \
        tini==0.18.0

    ENTRYPOINT ["tini", "-g", "--"]

.. code-block:: shell

    $ docker image ls myimage
    REPOSITORY          TAG                 IMAGE ID            CREATED             SIZE
    myimage             latest              da9de3dd648d        18 seconds ago      729MB


Step 2: Cleanup after a Conda install (633 MB)
----------------------------------------------

Files added to docker images are stored in immutable layers. After each command
the filesystem is checkpointed, and the diff from the previous command stored
as a layer (kind of like git). As such, it's best to have ``RUN`` commands that
install things using a package manager (like ``conda``) also cleanup extraneous
files after the install.

For ``conda``, the most thorough cleanup command is ``conda clean -afy``. This
removes cache files, package tarballs, and the entire package cache. To ensure
only necessary files are saved in each layer, you'll want to add this to the
end of any ``RUN`` command that installs packages with ``conda``.

.. code-block:: docker

    FROM continuumio/miniconda3:4.6.14

    RUN conda install --yes \
        nomkl \
        dask==1.2.2 \
        numpy==1.16.3 \
        pandas==0.24.2 \
        tini==0.18.0 \
        && conda clean -afy

    ENTRYPOINT ["tini", "-g", "--"]

.. code-block:: shell

    $ docker image ls myimage
    REPOSITORY          TAG                 IMAGE ID            CREATED             SIZE
    myimage             latest              1e28ae036d28        13 seconds ago      633MB


Step 3: Avoid updating existing packages (633 MB)
-------------------------------------------------

Just as you want to cleanup Conda's cache files at the end of each ``RUN``
command, you also want to ensure you don't update any installed packages.
Updates to packages will result in both the original version and the new
version being stored in layers in the image, increasing image size. The
``--freeze-installed`` flag tells Conda to avoid updating already installed
packages, and should be added to any ``install`` command. This isn't super
important for this image, but becomes more important if multiple rounds of
``conda install`` commands are used.

.. code-block:: docker

    FROM continuumio/miniconda3:4.6.14

    RUN conda install --yes --freeze-installed \
        nomkl \
        dask==1.2.2 \
        numpy==1.16.3 \
        pandas==0.24.2 \
        tini==0.18.0 \
        && conda clean -afy

    ENTRYPOINT ["tini", "-g", "--"]

.. code-block:: shell

    $ docker image ls myimage
    REPOSITORY          TAG                 IMAGE ID            CREATED             SIZE
    myimage             latest              b85824ca515e        16 seconds ago      633MB


Step 4: Remove additional unnecessary files (577 MB)
----------------------------------------------------

Besides the cache files removed above, ``conda`` also may install files that
aren't 100% necessary for your application. These are things that are included
in a ``conda`` package, but you may not need and end up just taking up space.
In our case, we remove the following:

- Python Bytecode Files: 54 MB

  Every Python source file installed by Conda has a corresponding bytecode
  cache file (``*.pyc``) installed as well. These files are redundant and can
  be removed. To prevent Python from recreating them at runtime we also set the
  ``PYTHONDONTWRITEBYTECODE`` environment variable

- Static Libraries: 42 MB

  Several packages come with static libraries that we won't be needing in our
  Docker image. Ideally these static libraries should be split into separate
  packages (I `filed
  <https://github.com/conda-forge/openssl-feedstock/issues/45>`__ `a few
  <https://github.com/conda-forge/openblas-feedstock/issues/69>`__ `issues
  <https://github.com/conda-forge/python-feedstock/issues/260>`__ on the major
  offenders, but this will take some time and community effort to fix). For now
  we can remove them manually.

- JavaScript Source Maps: 19 MB

  Several libraries (``bokeh``, ``jupyterlab``, etc...) distribute JavaScript
  source maps (``*.js.map``) as part of the library. These source maps are useful for
  debugging, but aren't needed in production and can be removed. As with the
  static libraries above, there are issues for removing these but they'll take
  time to handle.

- Unminified Bokeh JavaScript: 16 MB

  Bokeh distributes both minified and unminified JavaScript resources. We only
  use the minified version in Dask, so we can remove the unminified files.

Applying these changes to our Dockerfile:

.. code-block:: docker

    FROM continuumio/miniconda3:4.6.14

    ENV PYTHONDONTWRITEBYTECODE=true

    RUN conda install --yes --freeze-installed \
        nomkl \
        dask==1.2.2 \
        numpy==1.16.3 \
        pandas==0.24.2 \
        tini==0.18.0 \
        && conda clean -afy \
        && find /opt/conda/ -follow -type f -name '*.a' -delete \
        && find /opt/conda/ -follow -type f -name '*.pyc' -delete \
        && find /opt/conda/ -follow -type f -name '*.js.map' -delete \
        && find /opt/conda/lib/python*/site-packages/bokeh/server/static -follow -type f -name '*.js' ! -name '*.min.js' -delete

    ENTRYPOINT ["tini", "-g", "--"]

.. code-block:: shell

    $ docker image ls myimage
    REPOSITORY          TAG                 IMAGE ID            CREATED             SIZE
    myimage             latest              5744d3087c78        8 seconds ago       577MB


Step 5: Use a smaller base image (258 MB)
-----------------------------------------

So far we've been using the ``miniconda3`` base image provided by Anaconda.
This image is built on ``debian``, and has lots of features we don't need.
Instead, we can build our image on `Alpine Linux`_, a much slimmer base image.
Since Alpine Linux uses ``musl`` by default (while Conda packages are built on
``glibc``) we need to do some workarounds to keep everything working. These
patches have been applied, and a new miniconda base image is available at
`jcrist/alpine-conda
<https://cloud.docker.com/repository/docker/jcrist/alpine-conda>`__. This image
already has ``tini`` installed and sets ``PYTHONDONTWRITEBYTECODE``, so we can
drop those from our dockerfile.

Updating our Dockerfile:

.. code-block:: docker

    FROM jcrist/alpine-conda:4.6.8

    RUN /opt/conda/bin/conda install --yes --freeze-installed \
            dask==1.2.2 \
            numpy==1.16.3 \
            pandas==0.24.2 \
            nomkl \
        && /opt/conda/bin/conda clean -afy \
        && find /opt/conda/ -follow -type f -name '*.a' -delete \
        && find /opt/conda/ -follow -type f -name '*.pyc' -delete \
        && find /opt/conda/ -follow -type f -name '*.js.map' -delete \
        && find /opt/conda/lib/python*/site-packages/bokeh/server/static -follow -type f -name '*.js' ! -name '*.min.js' -delete

.. code-block:: shell

    $ docker image ls myimage
    REPOSITORY          TAG                 IMAGE ID            CREATED             SIZE
    myimage             latest              cfc76843c98c        51 seconds ago      258MB


Conclusion and Future Work
--------------------------

Applying the above steps we went from ``1.69 GB`` with our naive dockerfile
down to ``258 MB`` with the optimized version, ``~15%`` the size of the
original version! These images distribute much faster over the network, which
can lead to faster application startup on a fresh cluster.

The final images can be found in the `alpine-dask-docker`_ repository, and
should be direct drop ins for their debian-based counterparts found for the
standard `dask-docker images`_. In particular, they should work with the
existing `dask helm chart`_.

To make creating smaller images easier, some work is being done in the
Conda-Forge community to reduce package size - splitting out static libraries
and removing unnecessary files from the package.  Likewise, the above
techniques may be applied to the official Anaconda `miniconda3 base image`_.
If you're interested in this effort, please feel free to reach out to the
appropriate repos/feedstocks.


.. _conda: https://conda.io/docs/
.. _Docker: https://www.docker.com/
.. _Dask: https://dask.org/
.. _alpine-dask-docker:
.. _here: https://github.com/jcrist/alpine-dask-docker
.. _dask-docker images: https://github.com/dask/dask-docker
.. _dask helm chart: https://github.com/helm/charts/tree/master/stable/dask
.. _Alpine Linux: https://alpinelinux.org/
.. _miniconda3 base image: https://hub.docker.com/r/continuumio/miniconda3
.. _tini: https://github.com/krallin/tini
.. _Conda-Forge: https://conda-forge.org/
