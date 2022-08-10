.. _developer-tests:

Testing for Developers
======================

Running tests
-------------

Unit tests can be run with:

.. code-block:: bash

   $ tox

Linting can be run with:

.. code-block:: bash

  $ make lint

To run tests directly with pytest, or to integrate into your IDE, you can reference
``tox.ini`` for the appropriate commands and environment variable configuration.
Testing done without ``C7N_TEST_RUN`` and ``C7N_VALIDATE`` may not match ``tox`` results.

Operating System Compatibility
------------------------------

Tests are currently executed on both Ubuntu 1804 and Windows Server 2019
and must pass on both operating systems.

Both Windows and Linux sample dockerfiles are provided for running Tox which may help you.
You can find these in `tools/dev`.

In Docker for Windows you can run both of these containers,
`even simultaneously <https://docs.microsoft.com/en-us/virtualization/windowscontainers/deploy-containers/linux-containers>`_.


If you need access to Windows you can download a
`virtual machine <https://developer.microsoft.com/en-us/windows/downloads/virtual-machines>`_
directly from Microsoft for any hypervisor.


Writing Tests for Cloud Controlled Resources
--------------------------------------------

Cloud Custodian makes use of flight recording to allow for both
functional and unit testing. Each of the custodian providers uses a
separate technique that integrates with the provider sdk to handle
flight recording of custodian's api calls, we provide a common
abstraction over that in our testing framework via
record_flight_data/replay_flight_data/

For setting up infrastructure to execute/test policies against we use
the pytest-terraform library.

  - `Pytest Terraform <https://github.com/cloud-custodian/pytest-terraform>`_ a Pytest Plugin leveraging terraform to setup test environments

.. _Creating Tests:

Creating Cloud Resources with Terraform
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If a test requires pre-existing cloud resources in order to operate,
`pytest-terraform` is the preferred method for creating those
resources.  Pytest Terraform uses `Terraform <https://terraform.io>`_
to repeatably & reliably stand up cloud resources.  Make sure you have
installed terraform and the ``terraform`` command is available in your
shell's PATH.

.. code-block:: shell

  $ terraform version

In addition to a working terraform installation, credentials and configuration for the target cloud will need to be completed.
`Getting started with Terraform <https://learn.hashicorp.com/terraform>`_

Pytest Terraform looks for matching modules in the ``tests/terraform`` directory.
So for a test named ``test_file_example`` the terraform files for that test will be in ``tests/terraform/file_example``.

Here's an example terraform file for the upcoming example.
It is placed in ``tests/terraform/file_example/main.tf``.

  ::

    resource "local_file" "bar" {
       content = "bar!"
       filename = "${path.module}/bar.txt"
    }

When invoked, this terraform module will create a file ``bar.txt`` with the contents ``bar!``.

In order to access this terraform module, import and wrap a test
method with the ``@terraform`` decorator.  The decorator takes one
required positional argument, the name of the module, which in the
above example is ``file_example``.  In addition to the single
positional argument, there are `several keyword arguments
<https://github.com/cloud-custodian/pytest-terraform#usage>`_ to
control how the decorator operates.

The following code example demonstrates how to run and interact with the previous terraform file.

  .. code-block:: python
    :emphasize-lines: 1

    @terraform('file_example', replay=False)
    def test_file_example(file_example):
        assert file_example['local_file.bar.content'] == 'bar!'

When first creating a test, explicitly set the ``replay`` parameter to
``False``.  This will force terraform to run on each invocation of the
test and perform the flight recording function.

The outputs and results of the terraform run are available via the
fixture passed into the test method.  The fixture will always be named
after the terraform module supplied in the first parameter to the
decorator, in this case ``file_example``.  Pytest Terraform uses
JMSEPath lookups, so in order to get the content of the ``bar``
resource ``local_file.bar.content`` is supplied as the item for
lookup.

Run this test using the following command, which will also generate flight recordings for terraform:

  .. code-block:: shell

    $ pytest tests/path/to/test.py -s -v -k 'test_file_example'

This may take a little while as tests are typically interacting with the cloud.
All terraform state is recorded in the same directory of the terraform module as a ``tf_resources.json`` file.

  .. code-block:: shell

    $ ls tests/terraform/file_example/
    main.tf
    tf_resources.json

Each invocation of the test where replay is ``False``, the ``tf_resources.json`` contents are replaced and updated with that runs output.

When the test is completed, remove ``replay=False`` in order to switch to replay mode by default.

  .. code-block:: python
    :emphasize-lines: 1

    @terraform('file_example')
    def test_file_example(file_example):

        assert file_example['local_file.bar.content'] == 'bar!'

Now when the test is run it will use the data previously recorded terraform resources and not run terraform directly.
When committing your test, don't forget to include the ``tests/terraform/file_example`` directory!

If your test performs destructive actions against a cloud resource created by terraform, check out `Controlling Resource Cleanup`_

Recording Custodian Interactions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Cloud Custodian tests provide a pytest fixture, ``test``, that provides access to
common unittest methods (such as ``assertEqual``) as well as the placebo based test methods.
In order to write a placebo enabled test two helper methods are provided:

  - ``record_flight_data`` - use this when creating the test
  - ``replay_flight_data`` - use this when the test is completed

When first creating a test, use the ``record_flight_data`` method.  This will
contact the cloud and store all responses as files in the placebo directory
(``tests/data/placebo/``).  The method takes one parameter, which is the directory
name to store placebo output in and it must be unique across all tests.  For
example:

  .. code-block:: python
    :emphasize-lines: 2

    def test_example(test):
        session_factory = test.record_flight_data('test_example')

        policy = {
            'name': 'list-ec2-instances',
            'resource': 'aws.ec2',
        }

        policy = test.load_policy(
            policy,
            session_factory=session_factory
        )

        resources = policy.run()
        test.assertEqual(len(resources), 1)

Now run this test using the following command to generate the placebo data:

  .. code-block:: shell

    $ pytest tests/path/to/test.py -s -v

This may take a little while as the test is contacting AWS.
All responses are stored in the placebo directory, and can be viewed when the test is
finished.  It is not necessary to inspect these files, but they can be helpful
if the test is not behaving how you expect.

  .. code-block:: shell

    $ ls tests/data/placebo/test_example/
    ec2.DescribeInstances_1.json
    ec2.DescribeTags_1.json

If it is necessary to run the test again - for example, if the test fails, or if
it is not yet fully complete - you can run with ``record_flight_data`` as many
times as necessary.  The contents of the directory will be cleared each time the
test is run while ``record_flight_data`` is in place.

When the test is completed, change to using ``replay_flight_data``:

  .. code-block:: python
    :emphasize-lines: 2

    def test_example(self, test):
        session_factory = test.replay_flight_data('test_example')

        ...

Now when the test is run it will use the data previously recorded and will not
contact the cloud.  When committing your test, don't forget to include the
``tests/data/placebo/test_example`` directory!

Note: If it's necessary to delay CLI calls due to delays in the time it takes
for an attribute on a resource to be reflected in an API call or any other reason,
use ``test.recording`` to only sleep when recording json like so:

  .. code-block:: python

    import time

    ...

    def test_example(self, test):

        ...

        if test.recording:
            time.sleep(10)


Controlling Resource Cleanup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If terraform destroy command fails during cleanup, it will mark the test as failed.
For tests that perform destructive actions against terraform managed resources there is
an option to tune how pytest-terraform performs this cleanup operation.

There are three options available for the ``teardown`` parameter:

  - `terraform.TEARDOWN_ON`  - Always perform terraform cleanup, fail on error
  - `terraform.TEARDOWN_OFF` - Never perform the terraform cleanup
  - `terraform.TEARDOWN_IGNORE` - Always perform the terraform cleanup, ignore errors

In general, `TEARDOWN_ON` and `TEARDOWN_IGNORE` are used for test teardown.
For debugging purposes `TEARDOWN_OFF` is provided allowing test authors
to inspect cloud entities after each test run.

In this example we create a new SQS and a policy to delete it then assert it is
deleted. To avoid terraform erroring on teardown `TEARDOWN_IGNORE` is used.

  ::

    provider "aws" {}

    resource "aws_sqs_queue" "test_sqs" {
      name = "delete-me"
    }

The following test uses the above `sqs_delete` terraform module:

  .. code-block:: python

    from pytest_terraform import terraform


    @terraform('sqs_delete', teardown=terraform.TEARDOWN_IGNORE)
    def test_sqs_delete(test, sqs_delete):
        # Create a placebo record/replay session.
        session_factory = test.replay_flight_data("test_sqs_delete")
        client = session_factory().client("sqs")

        # Extract Queue ARN from terraform output
        queue_arn = sqs_delete["aws_sqs_queue.test_sqs.arn"]

        # Create a policy that will delete any matched resources
        p = test.load_policy(
            {
                "name": "sqs-delete",
                "resource": "sqs",
                "filters": [{"QueueArn": queue_arn}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        # Checks to make sure our single test queue was found
        test.assertEqual(len(resources), 1)

        # Extract the QueueURL from the filtered resource
        queue_url = resources[0]['QueueUrl']

        # Attempt to delete the queue and expect AWS API to produce an error
        pytest.raises(ClientError, client.purge_queue, QueueUrl=queue_url)

.. _Converting Tests:

Converting older functional tests
---------------------------------

Before the introduction of pytest-terraform many functional tests were wrapped
with ``@functional`` and used class-based tests which inherited ``BaseTest``.

To convert a previous functional testing to use the preferred pytest-terraform method
outlined above, first move the method to either a base class which does not inherit
``BaseTest`` as pytest does not support fixtures with unittest derived classes, alternatively
convert the test to a function.

Once the test method has been relocated, replace any references to ``@functional``
with the appropriate ``@terraform`` decorator from `Creating Cloud Resources with Terraform`_.

Finally, replace all mentions of ``self`` with the ``test`` fixture outlined in `Recording Custodian Interactions`_
Before committing any changes, the tests should be run explicitly in record mode
to capture all new changes in flight data.

Below is an example, older, functional test

.. code-block:: python

  class TestSqs(BaseTest):

      @functional
      def test_sqs_delete(self):
          session_factory = self.replay_flight_data("test_sqs_delete")
          client = session_factory().client("sqs")
          client.create_queue(QueueName="test-sqs")
          queue_url = client.get_queue_url(QueueName="test-sqs")["QueueUrl"]

          p = self.load_policy(
              {
                  "name": "sqs-delete",
                  "resource": "sqs",
                  "filters": [{"QueueUrl": queue_url}],
                  "actions": [{"type": "delete"}],
              },
              session_factory=session_factory,
          )
          resources = p.run()
          self.assertEqual(len(resources), 1)
          self.assertRaises(ClientError, client.purge_queue, QueueUrl=queue_url)
          if self.recording:
              time.sleep(60)


This can be replaced with a new ``sqs_delete`` terraform module and the following code:

.. code-block:: python

  from pytest_terraform import terraform


  @terraform('sqs_delete', teardown=terraform.TEARDOWN_IGNORE)
  def test_sqs_delete(test, sqs_delete):
      session_factory = test.replay_flight_data("test_sqs_delete")
      client = session_factory().client("sqs")

      queue_arn = sqs_delete["aws_sqs_queue.test_sqs.arn"]

      p = test.load_policy(
          {
              "name": "sqs-delete",
              "resource": "sqs",
              "filters": [{"QueueArn": queue_arn}],
              "actions": [{"type": "delete"}],
          },
          session_factory=session_factory,
      )

      resources = p.run()
      test.assertEqual(len(resources), 1)
      queue_url = resources[0]['QueueUrl']
      pytest.raises(ClientError, client.purge_queue, QueueUrl=queue_url)
