.. Cloud Custodian documentation master file, created by
   sphinx-quickstart on Mon Dec 21 08:34:24 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Cloud Custodian Documentation
=============================

Cloud Custodian is a tool that unifies the dozens of tools and scripts most organizations use for managing their AWS accounts into one open source tool. It's a stateless rules engine for policy definition and enforcement, with metrics and detailed reporting for AWS.

Organizations can use Custodian to manage their AWS environments by ensuring compliance to security policies, tag policies, garbage collection of unused resources, and cost management via off-hours resource management, all from the same place. Custodian policies are written in simple YAML configuration files that specify given resource types and are constructed from a vocabulary of filters and actions.

Navigate below and get started with Cloud Custodian!

.. toctree::
   :maxdepth: 2
   :caption: Introduction

   overview/index
   quickstart/index
   quickstart/usage
   quickstart/advanced

.. toctree::
   :maxdepth: 2
   :caption: Examples

   quickstart/offhours
   quickstart/tagCompliance
   usecases/index

.. toctree::
   :maxdepth: 2
   :caption: Working with AWS Lambda

   policy/lambda
   policy/mu

.. toctree::
   :maxdepth: 2
   :caption: Policies reference

   policy/index.rst
   filters

.. toctree::
   :maxdepth: 2
   :caption: Contributing

   contribute
   developer/index.rst
   developer/installing.rst
   developer/tests.rst

.. toctree::
   :maxdepth: 2
   :caption: Azure

   azure/index
   azure/contribute
   azure/authentication
   azure/usecases/index
   azure/policy/index

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   generated/modules


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
