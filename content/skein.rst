Introducing Skein: Deploy Python on Apache YARN the Easy Way
############################################################

:date: 2018-08-14 12:00
:category: skein
:tags: skein
:slug: introducing-skein
:author: Jim Crist
:summary: New tools to simplify deploying Python applications on Apache YARN.

Summary
-------

We introduce `a new tool and library <https://jcrist.github.io/skein/>`__ for
deploying applications on Apache YARN. We provide background on why this work
was necessary, and demonstrate deploying a simple Python application on a YARN
cluster.


Introduction
------------

`Apache YARN`_ is the resource management and job scheduling framework
native to Hadoop clusters. It is responsible for scheduling applications on the
cluster (deciding where and when an application gets the resources it
requested) and provisioning these resources in a secure and robust way.

Many data-processing frameworks (e.g. Spark, Flink, Storm, etc...) support YARN
as a deployment option. As a contributor to Dask_, I sought to improve our
deployment support for YARN. This proved difficult for several reasons:

- YARN is a JVM-only framework, and requires a non-trivial amount of Java to
  get things working (for example, Spark's YARN support is ~6000 lines of
  Scala). Dask is written in Python.

- Applications that deploy on YARN need to distribute their resources with
  them. For Java applications this is straightforward - just bundle everything
  into a JAR and you're done. With Python things aren't so easy.

- YARN security (if enabled) uses Kerberos_, which can be tricky to support
  properly. Kerberos is so difficult to get right that one of the core Hadoop
  developers `wrote a book
  <https://steveloughran.gitbooks.io/kerberos_and_hadoop/sections/kerberos_the_madness.html>`__
  where it's compared to the horrors found in `H.P. Lovecraft`_ novels. This,
  coupled with the myriad of configuration options YARN supports can makes
  testing applications difficult.


.. image:: /images/one-does-not-simply-deploy-on-yarn.jpg
    :width: 60 %
    :align: center
    :alt: sometimes things are difficult


I'm fairly happy with the set of tools we've developed to solve these problems.
The remainder of this post discusses them in detail.


Skein: Easy Deployment on YARN
------------------------------

Skein_ is a *declarative* tool for deploying applications on YARN. Users write
application specifications either in YAML or using the native Python API, and
Skein handles deploying and managing them on YARN.

Highlights:

- Skein applications are written declaratively using a specificatin reminiscent
  of `docker-compose`_. While YARN is extremely flexible, Skein is opinionated
  about how an application should be structured. Sane defaults and reduced
  options help simplify the user API and greatly reduce the amount of code
  needed to deploy on YARN.

- Every Skein application contains a `key-value store`_ running on the
  application master. This provides a way for containers to share runtime
  configuration parameters (e.g. dynamically chosen addresses and ports), as
  well as coordinate state between containers.

- Skein applications are dynamic. Containers can be started and stopped at
  runtime, allowing for services to scale to your needs.

- Skein was designed "API first", meaning both the `Python API`_ and `CLI`_ are
  first-class-citizens, and should (hopefully) feel natural and intuitive (if
  you find any rough edges, please `file an issue`_).

- Skein contains two (unfortunately necessary-ish) Java processes written as
  `gRPC`_ services. This provides a clear separation between the application
  language and Java, and means that other language bindings besides Python are
  possible, allowing other languages to take advantage of this work.

- Skein is tested on multiple Hadoop configurations, including both ``simple``
  and ``kerberos`` security, to help ensure support across all clusters.


Example: Echo Server
--------------------

To illustrate the intended workflow, we'll implement a simple echo server and
client, and use Skein to deploy on YARN.

The full code for this example can be found `here
<https://github.com/jcrist/skein/blob/master/examples/echo_server/>`__.


The Echo Server
~~~~~~~~~~~~~~~

The echo server is based off `this example
<https://docs.python.org/3/library/asyncio-stream.html#tcp-echo-server-using-streams>`__
from the asyncio docs. The full server code is available `here
<https://github.com/jcrist/skein/blob/master/examples/echo_server/server.py>`__.
Walking through some of the Skein-specific bits:

Since the server could be run on any machine, we may not be sure what ports are
available on that machine, or the host address of the machine as seen from the
edge node. To handle this we start the server on a dynamic port, and then
determine the hostname and port at runtime.

.. code-block:: python

    # Setup the server with a dynamically chosen port
    loop = asyncio.get_event_loop()
    coro = asyncio.start_server(handle_echo, '0.0.0.0', 0, loop=loop)
    server = loop.run_until_complete(coro)

    # Determine the dynamically chosen address
    host = socket.gethostbyname(socket.gethostname())
    port = server.sockets[0].getsockname()[1]
    address = '%s:%d' % (host, port)


To communicate this dynamic address back to the client, we store the address in
the `key-value store`_. To allow scaling up to multiple server instances (a bit
contrived for this example) we append the server's ``container_id`` to a fixed
prefix (``'address.'``) to ensure a unique key.


.. code-block:: python

    # Form a unique key to store the address using the current container id
    key = 'address.%s' % skein.properties.container_id


We then store the server address in the key-value store. Note that we set the
current ``container_id`` as the *owner* of the key. This makes use of Skein's
key-value store `ownership model`_. When the server's container exits (whether
successfully or due to failure), the key will be deleted. This helps ensure
that when servers shutdown their address is no longer available to the echo
client.


.. code-block:: python

    # Connect to the application master
    app = skein.ApplicationClient.from_current()

    # The key-value store only accepts bytes as values
    value = address.encode()

    # Store the server address in the key-value store, assigning the current
    # container as the owner of the key. This ensures that the key is deleted if
    # the container exits.
    app.kv.put(key, value, owner=skein.properties.container_id)

The remainder of the echo server implementation is generic ``asyncio``
operations - providing a handler, starting up the server, and running the event
loop until shutdown.


The Echo Client
~~~~~~~~~~~~~~~

The echo client is based off `this example
<https://docs.python.org/3/library/asyncio-stream.html#asyncio-tcp-echo-client-streams>`__
from the asyncio docs. The full client code is available `here
<https://github.com/jcrist/skein/blob/master/examples/echo_server/client.py>`__.
Walking through some of the Skein-specific bits:

When using either the `CLI`_ or the `Python API`_, most operations require an
*application id*. This is a unique identifier for your application in YARN, and
is used both by Skein and by external tools (for example, the ``yarn`` CLI
command). In our example echo-client here we provide the application id via the
command-line, and then use it to connect to the application

.. code-block:: python

    # Get the application id from the command-line args
    app_id = sys.argv[1]

    # Connect to the application
    app = skein.Client().connect(app_id)


Before we can send a message to the echo server, we first need to get its
address. This again is done through the `key-value store`_. However, instead of
getting the address of a single echo server, we'll loop through all registered
addresses and message each of them. To do this we use the `get_prefix
<https://jcrist.github.io/skein/api.html#skein.kv.KeyValueStore.get_prefix>`__
method to get all keys that start with ``address.``.

.. code-block:: python

    async def echo_all(app, message):
        """Send and recieve a message from all running echo servers"""
        # Loop through all registered server addresses
        for address in app.kv.get_prefix('address.').values():
            # Parse the host and port from the stored address
            host, port = address.decode().split(':')
            port = int(port)

            # Send the message to the echo server
            await tcp_echo_client(message, loop, host, port)


The remainder of the client implementation is generic - provide a async
function to message each server, start the event loop, and run until all
futures have completed.


Packaging the Python Environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Skein doesn't mandate a specific way of distributing application
files/executables. File resources may already exist on every node, or may need
to be distributed with the application. For Python applications, one way of
handling this is to use the `conda package manager`_ to create a Python
environment, and `conda-pack`_ to package that environment for distribution.
This is what we'll do here.

.. code-block:: console

    # Create a new environment with all dependencies
    $ conda create -y -n demo -c conda-forge python skein conda-pack
    ...

    # Activate the environment
    $ conda activate demo

    # Package the environment into environment.tar.gz
    $ conda-pack -o environment.tar.gz
    Collecting packages...
    Packing environment at '/home/jcrist/miniconda/envs/demo' to 'environment.tar.gz'
    [########################################] | 100% Completed | 16.6s

    # See the size of the output environment
    $ du -h environment.tar.gz
    102M    environment.tar.gz


During `YARN Resource Localization`_ this environment can then be unpacked and
linked as a directory in every container.

For more information on file distribution in Skein, see the `distributing files
docs`_.


The Application Specification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

With a completed server and client implementation, we now need to write the
application specification. We'll only make use of a few of the specification
fields here; the full schema can be found in the `specification docs`_.

The echo server specification can be found `here
<https://github.com/jcrist/skein/blob/master/examples/echo_server/spec.yaml>`__,
and is also duplicated below:

.. code-block:: yaml

    name: echoserver

    services:
        server:
            resources:
                vcores: 1
                memory: 256
            files:
                # A packaged conda environment to be distributed with the
                # application. During YARN resource localization this will be
                # automatically unpacked into the directory ``environment``.
                environment: environment.tar.gz
                # The server implementation.
                server.py: server.py
            commands:
                # Activate the conda environment
                - source environment/bin/activate
                # Start the server
                - python server.py

We define a single service ``server``, and specify that each instance needs
one virtual-core (usually equal to one CPU, cluster specific) and 256 MB of
memory. For file resources, we specify the packaged Conda environment, as well
as the server script. These will be mapped to ``./environment/`` and
``./server.py`` in the container environment respectively. Finally we provide a
list of commands to run to start the service. For some services this may be
more complicated, but here it's just activating the packaged Conda environment
and running the server script.


Running the Application
~~~~~~~~~~~~~~~~~~~~~~~

We're now ready to start the application. This could be done using the `Python
API`_, but here we'll make use of the `CLI`_.

.. code-block:: console

    # Start the application, and store the application id as APPID
    $ APPID=`skein application submit spec.yaml`

This validates the specification, uploads any necessary file resources to HDFS,
and then submits the application to YARN. To check on the status of the
application we can use the ``skein application status`` command:

.. code-block:: console

    # Check the application status
    $ skein application status $APPID
    APPLICATION_ID                    NAME          STATE      STATUS       CONTAINERS    VCORES    MEMORY    RUNTIME
    application_1534186866311_0009    echoserver    RUNNING    UNDEFINED    2             2         768       8s

This shows 2 running containers: one for the application master, and one for
our echo server. You can also navigate to the YARN Web-UI to check on the
status of the application, based on the given application ID:


.. image:: /images/skein_resourcemanager_echoserver.png
    :width: 90 %
    :align: center
    :alt: The YARN web-ui


Trying out our echo client:

.. code-block:: console

    $ python client.py $APPID
    Connecting to server at 172.18.0.4:41846
    Sent: 'Hello World!'
    Received: 'Hello World!'


And it works! We see communication with a single echo server; the dynamic
address was found at ``172.18.0.4:41846``, and the message was sent and
returned successfully.

Next, lets try scaling up the number of echo servers using the ``skein
container scale`` command:

.. code-block:: console

    # Scale to 4 server instances
    $ skein container scale $APPID --service server --number 4

    # List all ``server`` containers for this application
    $ skein container ls $APPID --service server
    SERVICE    ID          STATE      RUNTIME
    server     server_0    RUNNING    2m
    server     server_1    RUNNING    4s
    server     server_2    RUNNING    3s
    server     server_3    RUNNING    2s


Running the echo client again:

.. code-block:: console

    $ python client.py $APPID
    python client.py $APPID
    Connecting to server at 172.18.0.4:41846
    Sent: 'Hello World!'
    Received: 'Hello World!'
    Connecting to server at 172.18.0.4:42547
    Sent: 'Hello World!'
    Received: 'Hello World!'
    Connecting to server at 172.18.0.4:37295
    Sent: 'Hello World!'
    Received: 'Hello World!'
    Connecting to server at 172.18.0.4:45087
    Sent: 'Hello World!'
    Received: 'Hello World!'

This time we see communication with 4 different echo servers, one for each
server instance.

Finally, we can shutdown our application using the ``skein application
shutdown`` command:

.. code-block:: console

    # Shutdown the application
    $ skein application shutdown $APPID

    # Show the application was shutdown
    $ skein application status $APPID
    APPLICATION_ID                    NAME          STATE       STATUS       CONTAINERS    VCORES    MEMORY    RUNTIME
    application_1534186866311_0009    echoserver    FINISHED    SUCCEEDED    0             0         0         5m


Note that if the ``python server.py`` command exited itself (perhaps via a
``shutdown`` endpoint on the server), then the manual shutdown command wouldn't
be necessary. This can be nice for things like batch processing jobs that have
a distinct end, as they can then be submitted and run to completion without
further human intervention.

-----

To review, in the above example we

- Wrote a demo echo server and client.
- Added YARN deployment support using Skein
- Packaged the application dependencies using `conda-pack`_
- Started, scaled, and stopped the echo server on YARN

All without writing a line of Java. Additionally, the Python code that was
needed to support YARN deployment was relatively short. While this example was
simplistic, we've found that real-world applications (such as the dask-yarn_
library) remain just as clear and concise (although this is more of a testament
to Python than to Skein).


Testing Skein
-------------

As mentioned at the top, due to the myriad of configuration options, testing
that an application works on all YARN clusters can be difficult. The YARN
documentation `is pretty adamant about this
<https://hadoop.apache.org/docs/stable/hadoop-yarn/hadoop-yarn-site/YarnApplicationSecurity.html>`__

    If you don’t test your YARN application in a secure Hadoop cluster, it
    won’t work.

To test Skein, an external tool `hadoop-test-cluster`_ was developed. This is a
pip-installable tool for creating and working with tiny dockerized test
clusters. Images with both ``simple`` and ``kerberos`` security configurations
are available, and the tool is written to allow extending with further options.

Assuming you have docker already installed, using a kerberized test cluster is
as easy as

.. code-block:: console

    # Start the cluster, mounting the local directory
    $ htcluster startup --image kerberos --mount .:workdir

    # Login
    $ htcluster login

    # Or run a command externally
    $ htcluster exec -- py.test mylibrary

    # Shutdown the cluster
    $ htcluster shutdown

Making the tests easy to run locally has eased development, and helps ensure
Skein is robust across different Hadoop deployments.


Review and Future Work
----------------------

We presented three new tools:

- Skein_ for easy deployment of applications on YARN.
- conda-pack_ for packaging the dependencies of these applications for
  distribution.
- hadoop-test-cluster_ for no-fuss testing of Hadoop applications locally.

Taken together, these tools help provide a workflow for bringing Python
applications to a traditionally Java based ecosystem.

These tools are currently being used to deploy Dask on YARN in the `dask-yarn`_
libary. Similar work is being investigated for `deploying Ray on YARN
<https://github.com/ray-project/ray/issues/2214>`__, as well as adding a
non-Spark kernelspec to `Jupyter Enterprise Gateway
<https://github.com/jupyter-incubator/enterprise_gateway>`__.

If this workflow looks useful to you, please feel free to reach out on `github
<https://github.com/jcrist/skein>`__. Issues, pull-requests, and discussions
are welcome!

-----

*This work was made possible by my employer Anaconda Inc., as well as
contributions and feedback from the larger Python community*


.. -- Links --

.. _Apache YARN: https://hadoop.apache.org/docs/current/hadoop-yarn/hadoop-yarn-site/YARN.html
.. _YARN resource localization: https://hortonworks.com/blog/resource-localization-in-yarn-deep-dive/

.. _Dask: http://dask.pydata.org/
.. _conda package manager: https://conda.io/docs/
.. _conda-pack: https://conda.github.io/conda-pack/
.. _dask-yarn: http://dask-yarn.readthedocs.io/
.. _hadoop-test-cluster: https://github.com/jcrist/hadoop-test-cluster

.. _Kerberos: https://en.wikipedia.org/wiki/Kerberos_(protocol)
.. _H.P. Lovecraft: https://en.wikipedia.org/wiki/H._P._Lovecraft

.. _docker-compose: https://docs.docker.com/compose/overview/

.. _gRPC: http://grpc.io/

.. _Skein: https://jcrist.github.io/skein/
.. _CLI: https://jcrist.github.io/skein/cli.html
.. _Python API: https://jcrist.github.io/skein/api.html
.. _specification docs: https://jcrist.github.io/skein/specification.html
.. _distributing files docs: https://jcrist.github.io/skein/distributing-files.html
.. _key-value store: https://jcrist.github.io/skein/key-value-store.html
.. _ownership model: https://jcrist.github.io/skein/key-value-store.html#ownership

.. _file an issue: https://github.com/jcrist/skein/issues
