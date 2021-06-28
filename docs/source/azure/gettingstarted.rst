.. _azure_gettingstarted:

Getting Started
===============

.. _azure_write-policy:

Write your first policy
-----------------------

Cloud Custodian is a stateless rules engine that filters Azure resources and takes actions on based on policies that you define.

Cloud Custodian policies are expressed in YAML and include the following:

* The type of resource to run the policy against
* Filters to narrow down the set of resources
* Actions to take on the filtered set of resources

Our first policy filters to a VM of a specific name, then adds the tag ``Hello: World``.

Create a file named ``custodian.yml`` with the following content. Update ``my_vm_name`` to match an existing VM.

*Note: Some text editors (VSCode) inject invalid whitespace characters when copy/pasting YAML from a browser*

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

**Choose one of the supported authentication mechanisms**, and either log in to Azure CLI or set
environment variables as documented in :ref:`azure_authentication`.

.. code-block:: bash

    custodian run --output-dir=. custodian.yml

If successful, you should see output like the following on the command line::

    2016-12-20 08:35:06,133: custodian.policy:INFO Running policy my-first-policy resource: azure.vm
    2016-12-20 08:35:07,514: custodian.policy:INFO policy: my-first-policy resource:azure.vm has count:1 time:1.38
    2016-12-20 08:35:08,188: custodian.policy:INFO policy: my-first-policy action: tag: 1 execution_time: 0.67


You should also find a new ``my-first-policy`` directory with a log and a ``resources.json`` file.

See :ref:`filters` for more information on the features of the Value filter used in this sample.

.. _monitor-azure-cc:

(Optional) Run your policy with Azure Monitoring
""""""""""""""""""""""""""""""""""""""""""""""""

Cloud Custodian policies can emit logs and metrics to Application Insights when the policy executes.
Please refer to the :ref:`azure_monitoring` section for further details.

.. _azure_view_policy_reults:

View policy results
-------------------

The ``resources.json`` file shows you the raw data that results from your policy after filtering.  This file can help you understand the
fields available for your resources while developing your policy.

Custodian Report
"""""""""""""""""""""
Custodian has a report feature that allows the ``resources.json`` file to be viewed more concisely. 
By default, this will output data in a CSV format, but report also provides other output formats such as ``grid`` that are more digestable.

When run, the result will look like this::

    +------------+------------+-----------------+-------------------------------------+
    | name       | location   | resourceGroup   | properties.hardwareProfile.vmSize   |
    +============+============+=================+=====================================+
    | my_vm_name | westus     | my_vm_rg        | Standard_D2_v2                      |
    +------------+------------+-----------------+-------------------------------------+

The fields produced by ``custodian report`` vary by resource (i.e. properties.hardwareProfile.vmSize); however, you can add additional fields to your report 
by using the ``--field`` parameter. For example, if you want to see a list of tags on this resource:

.. code-block:: bash

    custodian report --output-dir=. --format grid --field tags=tags custodian.yml

Result::

    +------------+------------+-----------------+-------------------------------------+----------------------------+
    | name       | location   | resourceGroup   | properties.hardwareProfile.vmSize   | tagHeader                  |
    +============+============+=================+=====================================+============================+
    | my_vm_name | westus     | my_vm_rg        | Standard_D2_v2                      | {'custodian-tagged': True} |
    +------------+------------+-----------------+-------------------------------------+----------------------------+

The ``field`` parameter has the format ``--field header=field`` where header is the name of the column header in the report,
and field is the JMESPath of a specific field to include in the output. All available fields for a resource can be found in the ``resources.json`` file. 


Next Steps
----------
* :ref:`Notify users of policy violations using a Logic App <azure_examples_notifications_logic_app>`
* :ref:`More example policies <azure_examples>`
