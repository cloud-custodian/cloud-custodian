.. _developer-tests:

Testing for Developers
======================

Running tests
~~~~~~~~~~~~~

Unit tests can be run with:

.. code-block:: bash

   $ tox

Linting can be run with:

.. code-block:: bash

  $ make lint

Operating System Compatibility
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests are currently executed on both Ubuntu 1604 and Windows Server 2019
and must pass on both operating systems.

Both Windows and Linux sample dockerfiles are provided for running Tox which may help you.
You can find these in `tools/dev`.

In Docker for Windows you can run both of these containers,
`even simultaneously <https://docs.microsoft.com/en-us/virtualization/windowscontainers/deploy-containers/linux-containers>`_.


If you need access to Windows you can download a
`virtual machine <https://developer.microsoft.com/en-us/windows/downloads/virtual-machines>`_
directly from Microsoft for any hypervisor.

Decorating tests
~~~~~~~~~~~~~~~~

The ``functional`` decorator marks tests that don't require any pre-existing
AWS context, and can therefore be run cleanly against live AWS.

To run only the tests decorated by ``functional``:

.. code-block::

    (py37)$ pytest tests/test_vpc.py -x -m functional

Writing Placebo Tests for AWS Resources
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Note: These instructions are only for recording data in AWS. For Azure, GCP, or
other cloud providers, see the corresponding documentation for information on how
to record data there.

The `Placebo <http://placebo.readthedocs.io/en/latest/>`_ library is used to
record and replay AWS responses so that tests can run locally, and in a fraction
of the time it would take to interact with live AWS services.

In order to write a placebo test two helper methods are provided:

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

Now run this test using the following command to generate the placebo data:

  .. code-block:: shell

    $ nosetests -s -v tests/path/to/test.py

This may take a little while as the test is contacting AWS.
All responses are stored in the placebo dir, and can be viewed when the test is
finished.  It is not necessary to inspect these files, but they can be helpful
if the test is not behaving how you expect.

  .. code-block:: shell

    $ ls tests/data/placebo/test_example/
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

Note: if it's necessary to delay CLI calls due to delays in the time it takes
for an attribute on a resource to be reflected in an API call or any other reason,
use ``self.recording`` to only sleep when recording json like so:

  .. code-block:: python

    import time

    ...

    if self.recording:
      time.sleep(10)
