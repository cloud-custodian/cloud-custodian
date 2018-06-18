.. _azure_gettingstarted:

Getting Started
===============

* :ref:`azure_install-cc`
* :ref:`azure_write-policy`

.. _azure_install-cc:

Install Cloud Custodian and Azure Plugin
----------------------------------------

The Azure provider must be installed as a separate package in addition to c7n.

.. code-block:: bash

  $ virtualenv custodian
  $ source custodian/bin/activate
  (custodian) $ pip install c7n
  (custodian) $ pip install c7n_azure


If you prefer to install the latest from source control you can do so as follows:

.. code-block:: bash

  $ git clone https://github.com/capitalone/cloud-custodian.git
  $ virtualenv custodian
  $ source custodian/bin/activate
  (custodian) $ pip install cloud-custodian
  (custodian) $ pip install cloud-custodian/tools/c7n_azure

.. _azure_write-policy:

Write your first policy
-----------------------

A policy specifies the following items:

* The type of resource to run the policy against
* Filters to narrow down the set of resources
* Actions to take on the filtered set of resources

For this tutorial we will add a tag to all virtual machines with the name "Hello" and the value "World".

Create a file named ``custodian.yml`` with this content:

.. code-block:: yaml

    policies:
        - name: my-first-policy
          description: |
            Adds a tag to all virtual machines
          resource: azure.vm
          actions:
           - type: tag
             tag: Hello
             value: World

.. _azure_run-policy:

Run your policy
---------------

First, choose one of the supported authentication mechanisms and either log in to Azure CLI or set
environment variables as documented in :ref:`azure_authentication`.

.. code-block:: bash

    custodian run --output-dir=. custodian.yml

If successful, you should see output similar to the following on the command line::

    2016-12-20 08:35:06,133: custodian.policy:INFO Running policy my-first-policy resource: azure.vm
    2016-12-20 08:35:07,514: custodian.policy:INFO policy: my-first-policy resource:ec2 has count:1 time:1.38
    2016-12-20 08:35:08,188: custodian.policy:INFO policy: my-first-policy action: tag: 1 execution_time: 0.67


You should also find a new ``my-first-policy`` directory with a log and other
files (subsequent runs will append to the log by default rather than
overwriting it).

