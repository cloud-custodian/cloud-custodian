.. _azure_gettingstarted:

Getting Started
===============

* :ref:`azure_install-cc`
* :ref:`azure_write-policy`

.. _azure_install-cc:

Install Cloud Custodian and Azure Plugin
----------------------------------------

Cloud Custodian is a Python application and supports Python 2 and 3 on Linux and Windows.
We recommend using Python 3.6 or higher.

The Azure provider is an additional package which is installed in addition to c7n.

Option 1: Install latest from the repository
"""""""""""""""""""""""""""""""""""""""""""""

.. code-block:: bash

    $ git clone https://github.com/cloud-custodian/cloud-custodian.git
    $ cd cloud-custodian
    $ pip install -e .
    $ pip install -e tools/c7n_azure


.. _azure_write-policy:

Write your first policy
-----------------------

A policy specifies the following items:

* The type of resource to run the policy against
* Filters to narrow down the set of resources
* Actions to take on the filtered set of resources

For this tutorial we will filter to a VM of a specific name, then add the tag ``Hello: World``.

Create a file named ``custodian.yml`` with this content, and update ``my_vm_name`` to match an existing VM.

*note: Some text editors (VSCode) inject invalid whitespace characters when copy/pasting YAML from a browser*

.. code-block:: yaml

    policies:
        - name: my-first-policy
          description: |
            Adds a tag to a virtual machines
          resource: azure.vm
          filters:
            - type: value
              key: name
              value: my_vm_name
          actions:
           - type: tag
             tag: Hello
             value: World

.. _azure_run-policy:

Run your policy
---------------

First, **choose one of the supported authentication mechanisms** and either log in to Azure CLI or set
environment variables as documented in :ref:`azure_authentication`.

.. code-block:: bash

    custodian run --output-dir=. custodian.yml

If successful, you should see output similar to the following on the command line::

    2016-12-20 08:35:06,133: custodian.policy:INFO Running policy my-first-policy resource: azure.vm
    2016-12-20 08:35:07,514: custodian.policy:INFO policy: my-first-policy resource:ec2 has count:1 time:1.38
    2016-12-20 08:35:08,188: custodian.policy:INFO policy: my-first-policy action: tag: 1 execution_time: 0.67


You should also find a new ``my-first-policy`` directory with a log and a ``resources.json``.  The ``resources.json``
file shows you the raw data that results from your policy after filtering is applied.  This file can help you understand the
fields available for your resources while developing your policy.

See :ref:`filters` for more information on the features of the Value filter used in this sample.

.. _monitor-azure-cc:

Monitor Azure
-------------

Cloud Custodian policies can emit logs and metrics to Application Insights when the policy executes.
Please refer to the :ref:`azure_appinsightslogging` section for further details.


Next Steps
----------
* :ref:`Notify users of policy violations using a Logic App <azure_examples_notifications_logic_app>`
* :ref:`More example policies <azure_examples>`
