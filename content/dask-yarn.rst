Deploying Dask on YARN
######################

:date: 2018-08-15 16:00
:category: dask
:tags: dask, skein
:slug: dask-on-yarn
:author: Jim Crist
:summary: Development status of deploying Dask on YARN


Summary
-------

We present dask-yarn_, a library for deploying Dask_ on `Apache YARN`_. We
discuss the status of this tool, and possibilities for future work.


Introduction
------------

`Apache YARN`_ is the resource management and job scheduling framework native
to Hadoop clusters. Many data-processing frameworks like Spark or Flink support
YARN as a deployment option. As a contributor to Dask_, I sought to improve
our YARN support. This work resulted in two new libraries:

- Skein_ - a generic library for deploying applications on YARN (you can read
  more about this library in `my previous blogpost
  <http://jcrist.github.io/introducing-skein.html>`__).
- Dask-Yarn_ - a library for deploying Dask on YARN, using Skein as the backend.

These tools empower users to use Dask for data-engineering tasks on Hadoop
clusters, providing access to a field traditionally occupied by Spark and other
"big-data" tools. If you use a Hadoop cluster and have been wanting to try
Dask, I hope you'll give dask-yarn a try.


Usage
-----

Dask-Yarn provides an implementation of Dask's ``Cluster`` interface. This
is the same interface provided by other Dask deployment libraries like
`dask-kubernetes`_ and `dask-jobqueue`_. It provides methods for starting,
stopping, and scaling a Dask cluster on YARN, all from within Python.

The library currently is intended to be used from an edge node - user driving
code (whether a script or an interactive terminal) is run on the edge node,
while Dask's scheduler and workers are run in YARN containers. For comparison,
this is similar to `Spark's client mode
<https://spark.apache.org/docs/latest/running-on-yarn.html#launching-spark-on-yarn>`__
for YARN deployment. In the future a ``dask-yarn submit`` command may be
developed to allow submitting the driving code to also run in a container as
part of the application (similar to ``spark-submit`` in cluster mode).

Dask-Yarn is agnostic to how Python environments are managed, but provides
special support for distributing Conda_ environments packaged using
conda-pack_. If an alternative method is desired, users can specify this by
providing their own specification_. Please see `Distributing Python
Environments
<https://dask-yarn.readthedocs.io/en/latest/#distributing-python-environments>`__
in the dask-yarn documentation for more information.


Example
~~~~~~~

Here we provide a quick example of starting and using a Dask cluster on YARN.
This assumes you're logged into the edge node and Conda_ is available.

First, we create a new conda environment for our dependencies.

.. code-block:: console

    # Create a new conda environment for our dependencies
    $ conda create -n demo -c conda-forge dask-yarn conda-pack ipython pyarrow
    ...

    # Activate the environment
    $ conda activate demo


Next we package this environment for distribution. We can do this using the
``conda pack`` command. This packages the environment into a relocatable
tarball so it can be distributed to the YARN containers.


.. code-block:: console

    # Package the environment into environment.tar.gz
    $ conda pack -o environment.tar.gz
    Collecting packages...
    Packing environment at '/home/jcrist/miniconda/envs/demo' to 'environment.tar.gz'
    [########################################] | 100% Completed | 45.8s


Now we can launch a Dask cluster and use it to do some work. We'll work
interactively in IPython, but the same code could be part of a
script/application.

To start a cluster we create a ``YarnCluster`` object. We'll create a cluster
with 4 workers, each with 4 GB of memory and 2 cores.


.. code-block:: python

    In [1]: from dask_yarn import YarnCluster

    In [2]: cluster = YarnCluster(environment='environment.tar.gz',
    ...:                          worker_vcores=2,
    ...:                          worker_memory='4GB'
    ...:                          n_workers=4)


Next we connect to the cluster by creating a ``dask.distributed.Client``.


.. code-block:: python

    In [3]: from dask.distributed import Client

    In [4]: client = Client(cluster)

    In [5]: client
    Out[5]: <Client: scheduler='tcp://172.18.0.2:36217' processes=4 cores=8>


From the above we can see that we have 4 workers, and 8 cores total. You can
verify things are indeed running on YARN by checking the YARN Web-UI. You'll
need the application id, which is available as an attribute on the
``YarnCluster`` object.


.. code-block:: python

    In [6]: cluster.app_id
    Out[6]: 'application_1534359864394_0001'


.. image:: /images/dask-yarn-resourcemanager.png
    :width: 90 %
    :align: center
    :alt: YARN Web-UI


Now we can do whatever computations we want to do. Perhaps we want to read some
parquet files off of HDFS and compute a few statistics.

.. code-block:: python

    In [7]: ddf = dd.read_parquet('hdfs:///user/jcrist/nycflights.parquet')

    In [8]: ddf.groupby(ddf.Origin).DepDelay.mean().compute()
    Out[8]:
    Origin
    EWR     9.308481
    JFK    10.118569
    LGA     6.939973
    Name: DepDelay, dtype: float64


The number of workers can be scaled up and down dynamically as needed using the
``YarnCluster`` object.

.. code-block:: python

    In [9]: cluster.scale(8)  # Scale up to 8 workers

    In [10]: len(cluster.workers())
    Out[10]: 8

    In [11]: cluster.scale(2)  # Scale down to 2 workers

    In [12]: len(cluster.workers())
    Out[12]: 2


When you're done, you can manually shutdown the cluster by calling the
``YarnCluster.shutdown`` method. If you don't manually call ``shutdown``, the
cluster will be automatically shutdown on exit.

.. code-block:: python

    In [13]: cluster.shutdown()


When is this Useful?
--------------------

This functionality brings Dask to anyone that has access to a cluster edge
node. If you can run ``spark submit`` on your cluster, then dask-yarn should
work fine for you. This allows Dask to be used for many data-engineering tasks,
bringing Dask to a field traditionally occupied by Spark and other "big-data"
tools.

For users without direct access to the cluster this may be less useful. One
possibility for bringing support to users with restricted access is to build a
service similar to Livy_ that runs on an edge node and securely proxies
connections to Dask clusters running on YARN. See `this issue
<https://github.com/dask/distributed/issues/2043>`__ for more discussion.


Conclusion and Future Work
--------------------------

Is this tool useful for you? Are there missing features that would make it more
useful? Please `let us know <https://github.com/dask/dask-yarn/issues>`__! Feedback
is critical to improving the deployment experience for everyone.

In the immediate future I plan to add support for `adaptive deployments`_, as
well as a ``dask-yarn`` CLI to allow submitting jobs to run on the cluster
(similar to ``spark-submit`` in cluster mode).

-----

*This work was made possible by my employer Anaconda Inc., as well as
contributions and feedback from the larger Python community*


.. _dask-yarn: http://dask-yarn.readthedocs.io/
.. _conda: https://conda.io/docs/
.. _conda-pack: https://conda.github.io/conda-pack/
.. _dask-kubernetes: https://dask-kubernetes.readthedocs.io/
.. _dask-jobqueue: https://dask-jobqueue.readthedocs.io/
.. _Skein: https://jcrist.github.io/skein/
.. _Dask: http://dask.pydata.org/
.. _Apache YARN: https://hadoop.apache.org/docs/current/hadoop-yarn/hadoop-yarn-site/YARN.html
.. _specification: https://jcrist.github.io/skein/specification.html
.. _Livy: http://livy.incubator.apache.org/
.. _adaptive deployments: http://dask.pydata.org/en/latest/setup/adaptive.html
