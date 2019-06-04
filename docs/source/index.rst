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

   overview
   overview/index
   quickstart/index
   filters
   actions
   quickstart/advanced
   quickstart/policyStructure
   overview/glossary
   overview/deployment

.. toctree::
   :maxdepth: 2
   :caption: AWS

   aws/gettingstarted
   aws/examples/index
   aws/policy/index
   aws/aws-modes
   aws/usage
   aws/policy/lambda
   aws/policy/mu

.. toctree::
   :maxdepth: 1
   :caption: Azure

   azure/gettingstarted
   azure/authentication
   azure/examples/index
   azure/policy/index
   azure/azure-modes
   azure/advanced/index
   azure/contribute

.. toctree::
   :maxdepth: 1
   :caption: GCP

   gcp/gettingstarted
   gcp/gcp-modes

.. toctree::
   :maxdepth: 2
   :caption: Tools

   tools/c7n-org
   tools/c7n-policystream
   tools/c7n-mailer
   tools/c7n-trailcreator

.. toctree::
   :maxdepth: 2
   :caption: Contributing

   contribute
   developer/index.rst
   developer/installing.rst
   developer/tests.rst
   developer/documentation.rst


