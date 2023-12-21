.. Cloud Custodian documentation master file, created by
   sphinx-quickstart on Mon Dec 21 08:34:24 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Cloud Custodian Documentation
=============================

Cloud Custodian is a tool that unifies the dozens of tools and scripts
most organizations use for managing their public cloud accounts into
one open source tool. It uses a stateless rules engine for policy
definition and enforcement, with metrics, structured outputs and
detailed reporting for clouds infrastructure. It integrates tightly
with serverless runtimes to provide real time remediation/response with
low operational overhead.

Organizations can use Custodian to manage their cloud environments by
ensuring compliance to security policies, tag policies, garbage
collection of unused resources, and cost management from a single
tool. 

Cloud Custodian can be bound to serverless event streams across multiple cloud providers that maps to security, operations, and governance use cases.
Custodian adheres to a compliance as code principle, so you can validate, dry-run, and review changes to your policies.

Cloud Custodian policies are expressed in YAML and include the following:

* The type of resource to run the policy against
* Filters to narrow down the set of resources
* Actions to take on the filtered set of resources

Navigate below to your cloud provider and get started with Cloud Custodian!

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
   aws/usage
   aws/lambda
   aws/topics/index
   aws/contribute
   aws/resources/index

.. toctree::
   :maxdepth: 2
   :caption: Azure

   azure/gettingstarted
   azure/configuration/index
   azure/examples/index
   azure/advanced/index
   azure/resources/index

.. toctree::
   :maxdepth: 1
   :caption: GCP

   gcp/gettingstarted
   gcp/examples/index
   gcp/policy/index
   gcp/contribute
   gcp/resources/index

.. toctree::
   :maxdepth: 1
   :caption: Oracle Cloud Infrastructure (OCI)

   oci/gettingstarted
   oci/examples/index
   oci/testing
   oci/resources/index
   oci/advanced/index

.. toctree::
   :maxdepth: 1
   :caption: Tencent Cloud

   tencentcloud/gettingstarted
   tencentcloud/resources/index

.. toctree::
   :maxdepth: 1
   :caption: Kubernetes

   kubernetes/gettingstarted
   kubernetes/controllermode
   kubernetes/examples/index

.. toctree::
   :maxdepth: 2
   :caption: Tools

   tools/c7n-org
   tools/c7n-mailer
   tools/c7n-left
   tools/c7n-kube
   tools/cask
   tools/c7n-logexporter
   tools/c7n-trailcreator
   tools/c7n-policystream   
   tools/omnissm
   tools/c7n-guardian
   tools/c7n-salactus


.. toctree::
   :maxdepth: 2
   :caption: Contributing

   contribute
   developer/index.rst
   developer/installing.rst
   developer/tests.rst
   developer/documentation.rst
   developer/packaging.rst
