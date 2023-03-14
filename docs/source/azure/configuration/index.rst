.. _azure_configuration:

Configuring Azure Policies
==========================

Understand your options for authentication, hosting strategies, and monitoring 
the results of policies.

.. toctree::
  :maxdepth: 2
  :titlesonly:
  :glob:

  authentication
  monitoring

Hosting Options
---------------

The Azure provider for Cloud Custodian can be hosted by Azure Functions or in a containerized environment
like ACI or AKS. Both hosting options have periodic and event based execution modes.

For a quick and inexpensive start to running custodian policies, Azure Functions are a good hosting
strategy. The Azure Container Host requires more up-front configuration, but can make running a 
large number of policies against multiple subscriptions more maintainable.

.. toctree::
  :maxdepth: 2
  :titlesonly:
  :glob:

  functionshosting
  containerhosting
  ./acitutorial.rst
  ./helmtutorial.rst