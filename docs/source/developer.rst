.. _developer:

Developer Guide
===============

Requirements
------------

The Custodian requires Python 2.7, and a make/C toolchain.

On Linux
~~~~~~~~

.. code-block:: bash

   sudo apt-get install python python-dev python-pip python-virtualenv

On Mac
~~~~~~

.. code-block:: bash

   brew install python

Installing
----------

First, clone the repository:

.. code-block:: bash

   $ git clone https://github.com/capitalone/cloud-custodian.git
   $ cd cloud-custodian

Then build the software:

.. code-block:: bash

   $ make develop

Once that completes, make sure you load the virtualenv into your current shell:

.. code-block:: bash

   $ source bin/activate

You should have the ``custodian`` command available now:

.. code-block:: bash

   $ custodian -h

Testing
-------

Running tests
~~~~~~~~~~~~~

Unit tests can be run with:

.. code-block:: bash

   $ make test

Coverage reports can be generated and viewed with the following:

.. code-block:: bash

   $ make coverage

   # Open the reports in a browser

   # on osx
   $ open coverage/index.html

   # on gnomeish linux
   $ gnome-open coverage/index.html

Decorating tests
~~~~~~~~~~~~~~~~

The ``functional`` decorator marks tests that don't require any pre-existing
AWS context, and can therefore be run cleanly against live AWS.

Writing Placebo Tests
~~~~~~~~~~~~~~~~~~~~~

The `Placebo <http://placebo.readthedocs.io/en/latest/>`_ library is used to
simulate AWS responses so that tests can run locally, and in a fraction of the
time it would take to interact with live AWS services.

In order to write a placebo test two helper functions are provided:

  - `record_flight_data` - use this when creating the test
  - `replay_flight_data` - use this when the test is completed

When first creating a test, use the `record_flight_data` method.  This will
contact AWS and store all responses as files in the placebo directory
(`tests/data/placebo/`).  The method takes one parameter, which is the directory
name to store placebo output in and it must be unique across all tests.  For
example:

  .. code-block:: python
    :emphasize-lines: 2,3

    def test_example(self):
        session_factory = self.record_flight_data(
            'test_example')

        policy = {
            'name': 'list-ec2-instances',
            'resource': 'ec2'
        }
            
        policy = self.load_policy(
            policy,
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)

Now run this test via nosetest.  This may take a little while as the test is
contacting AWS.  All responses are stored in the placebo dir, and can be viewed
when the test is finished:

  .. code-block:: shell

    $ ls -1 tests/data/placebo/test_example/
    ec2.DescribeInstances_1.json
    ec2.DescribeTags_1.json

If it is necessary to run the test again - for example, if the test fails, or if
it is not yet fully complete - you can run with `record_flight_data` as many
times as necessary.  The contents of the directory will be cleared each time the
test is run while `record_flight_data` is in place.

When the test is completed, change to using `replay_flight_data`:

  .. code-block:: python
    :emphasize-lines: 2,3

    def test_example(self):
        session_factory = self.replay_flight_data(
            'test_example')

        ...

Now when the test is run it will use the data previously recorded and will not
contact AWS.  When committing your test, don't forget to include the 
`tests/data/placebo/test_example` directory!
