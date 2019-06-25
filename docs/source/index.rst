.. Cloud Custodian documentation master file, created by
   sphinx-quickstart on Mon Dec 21 08:34:24 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Cloud Custodian Documentation
=============================

Cloud Custodian is a tool that unifies the dozens of tools and scripts
most organizations use for managing their public cloud accounts into
one open source tool. It's a stateless rules engine for policy
definition and enforcement, with metrics, structured outputs and
detailed reporting for clouds infrastructure. It integrates tightly
with serverless runtimes to provide real time remediation/response with
low operational overhead.

Organizations can use Custodian to manage their cloud environments by
ensuring compliance to security policies, tag policies, garbage
collection of unused resources, and cost management from a single
tool. Custodian policies are written in simple YAML configuration
files that specify given resource types and are constructed from a
vocabulary of filters and actions. Custodian adheres to a compliance
as code principle, so you can validate, dry-run, and code review on
changes to your policies.

Navigate below and get started with Cloud Custodian!

.. toctree::
   :maxdepth: 2
   :caption: Introduction

   quickstart/index
   filters
   actions
   quickstart/advanced
   quickstart/policyStructure
   deployment

.. toctree::
   :maxdepth: 1
   :caption: AWS

   aws/gettingstarted
   aws/examples/index
   aws/aws-modes
   aws/usage
   aws/lambda
   aws/resources/index

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
   azure/resources/index

.. toctree::
   :maxdepth: 1
   :caption: GCP

   gcp/gettingstarted
   gcp/gcp-modes
   gcp/examples/index
   gcp/policy/index
   gcp/contribute
   gcp/resources/index


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


