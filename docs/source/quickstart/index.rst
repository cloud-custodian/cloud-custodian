.. _quickstart:

Getting Started
===============

See also the readme in the GitHub repository.

* :ref:`install-cc`
* :ref:`explore-cc`
* :ref:`cloud-providers`
* :ref:`monitor-cc`
* :ref:`tab-completion`

.. _install-cc:

Install Cloud Custodian
-----------------------

To install Cloud Custodian, just run::

  $ python3 -m venv custodian
  $ source custodian/bin/activate
  (custodian) $ pip install c7n

.. _explore-cc:

Explore Cloud Custodian
-----------------------

Run ``custodian -h`` to see a list of available commands.

Run ``custodian schema`` to see the complete list of cloud resources against
which you can run policies. To invoke command-line help with more information
about policy schema details, run ``custodian schema -h``.

Run ``custodian schema <cloud-provider>`` to see the available resources for a
specific cloud provider: ``custodian schema aws``

Run ``custodian schema <cloud-provider>.<resource>`` to see the available
filters and actions for each resource.

Drill down to get more information about available policy settings for each
resource, where the model for the command is::

  $ custodian schema <cloud>.<resource>.<category>.<item>

For example::

  $ custodian schema aws.s3.filters.is-log-target

provides the following information::

  Help
  ----

  Filter and return buckets are log destinations.

  Not suitable for use in lambda on large accounts, This is a api
  heavy process to detect scan all possible log sources.

  Sources:
    - elb (Access Log)
    - s3 (Access Log)
    - cfn (Template writes)
    - cloudtrail

  :example:

      .. code-block: yaml

          policies:
            - name: s3-log-bucket
              resource: s3
              filters:
                - type: is-log-target

  Schema
  ------
  
  {   'additionalProperties': False,
      'properties': {   'type': {   'enum': ['is-log-target']},
                        'value': {   'type': 'boolean'}},
      'required': ['type'],
      'type': 'object'}


Additionally, you can use the schema command to view information on the different
supported modes in Cloud Custodian::

  $ custodian schema mode

.. _cloud-providers:

Cloud Provider Specific Help
----------------------------

For specific setup isntructions for AWS, Azure, and GCP, visit the relevant getting started
page.

- :ref:`AWS <aws-gettingstarted>`
- :ref:`Azure <azure_gettingstarted>`
- :ref:`GCP <gcp_gettingstarted>`

Troubleshooting & Tinkering
+++++++++++++++++++++++++++

The policy is validated automatically when you run it, but you can also
validate it separately:

.. code-block:: bash

  $ custodian validate custodian.yml

You can also check which resources are identified by the policy, without
running any actions on the resources:

.. code-block:: bash

  $ custodian run --dryrun -s . custodian.yml

.. _monitor-cc:

Monitor resources
-----------------

Additional commands let you monitor your services in detail.

You can generate metrics, log outputs, and output to blob storage in each of the different
providers (AWS, Azure, Google Cloud Platform).

For detailed instructions on how to add metrics, logging, and blob storage output for the
different clouds, check out the cloud provider specific pages:

- :ref:`AWS <aws-gettingstarted>`
- :ref:`Azure <azure_gettingstarted>`
- GCP <tbd>

For details, see :ref:`usage`.

.. _tab-completion:

Tab Completion
--------------

To enable command-line tab completion for `custodian` on bash do the following one-time steps:

Run:

.. code-block:: bash

    activate-global-python-argcomplete

Now launch a new shell (or refresh your bash environment by sourcing the appropriate
file).

Troubleshooting
+++++++++++++++

If you get an error about "complete -D" not being supported, you need to update bash.
See the "Base Version Compatability" note `in the argcomplete docs
<https://argcomplete.readthedocs.io/en/latest/#global-completion>`_:

If you have other errors, or for tcsh support, see `the argcomplete docs
<https://argcomplete.readthedocs.io/en/latest/#activating-global-completion>`_.

If you are invoking `custodian` via the `python` executable tab completion will not work.
You must invoke `custodian` directly.
