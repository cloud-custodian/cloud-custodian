.. image:: https://badges.gitter.im/capitalone/cloud-custodian.svg
     :target: https://gitter.im/capitalone/cloud-custodian?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge
     :alt: Join the chat at https://gitter.im/capitalone/cloud-custodian

.. image:: https://ci.cloudcustodian.io/api/badges/capitalone/cloud-custodian/status.svg
     :target: https://ci.cloudcustodian.io/capitalone/cloud-custodian
     :alt: Build Status

.. image:: https://img.shields.io/badge/license-Apache%202-blue.svg
     :target: https://www.apache.org/licenses/LICENSE-2.0
     :alt: License

.. image:: https://coveralls.io/repos/github/capitalone/cloud-custodian/badge.svg?branch=master
     :target: https://coveralls.io/github/capitalone/cloud-custodian?branch=master
     :alt: Coverage

.. image:: https://requires.io/github/capitalone/cloud-custodian/requirements.svg?branch=master
     :target: https://requires.io/github/capitalone/cloud-custodian/requirements/?branch=master
     :alt: Requirements Status


Cloud Custodian
---------------

Cloud Custodian is a rules engine for AWS fleet management. It
allows users to define policies to enable a well managed cloud infrastructure,
that's both secure and cost optimized. It consolidates many of the adhoc
scripts organizations have into a lightweight and flexible tool, with unified
metrics and reporting.

Custodian can be used to manage AWS accounts by ensuring real time
compliance to security policies (like encryption and access requirements),
tag policies, and cost management via garbage collection of unused resources
and off-hours resource management.

Custodian policies are written in simple YAML configuration files that
enable users to specify policies on a resource type (ec2, asg, redshift, etc)
and are constructed from a vocabulary of filters and actions.

It integrates with lambda and cloudwatch events to provide for
real time enforcement of policies with builtin provisioning of the lambdas, or
as a simple cron job on a server to execute against large existing fleets.

“`Engineering the Next Generation of Cloud Governance <https://cloudrumblings.io/cloud-adoption-engineering-the-next-generation-of-cloud-governance-21fb1a2eff60>`_” by @drewfirment


Features
########

- Comprehensive support for AWS services and resources (~60), along with
  ~160 actions and ~180 filters to build policies with.
- Supports arbitrary filtering on resources with nested boolean conditions.
- Dry run any policy to see what it would do.
- Automatically provisions lambda functions, config rules, and cloud watch event targets for
  real-time policies.
- Cloudwatch metrics outputs on resources that matched a policy
- Structured outputs into s3 of which resources matched a policy.
- Intelligent cache usage to minimize api calls.
- Battle-tested - in production on some very large AWS accounts.
- Supports cross-account usage via STS role assumption.
- Supports integration with custom/user supplied lambdas as actions.

Links
#####

- `Homepage <https://developer.capitalone.com/opensource-projects/cloud-custodian>`_
- `Docs <http://www.capitalone.io/cloud-custodian/docs/>`_
- `Developer Install <http://www.capitalone.io/cloud-custodian/docs/developer/installing.html>`_


Quick Install
#############

::

  $ virtualenv --python=python2 custodian
  $ source custodian/bin/activate
  (custodian) $ pip install c7n


Usage
#####

First a policy file needs to be created in YAML format, as an example::

  policies:
  - name: remediate-extant-keys
    description: |
      Scan through all s3 buckets in an account and ensure all objects
      are encrypted (default to AES256).
    resource: s3
    actions:
      - encrypt-keys

  - name: ec2-require-non-public-and-encrypted-volumes
    resource: ec2
    description: |
      Provision a lambda and cloud watch event target
      that looks at all new instances and terminates those with
      unencrypted volumes.
    mode:
      type: cloudtrail
      events:
          - RunInstances
    filters:
      - type: ebs
        key: Encrypted
        value: false
    actions:
      - terminate

  - name: tag-compliance
    resource: ec2
    description: |
      Schedule a resource that does not meet tag compliance policies
      to be stopped in four days.
    filters:
      - State.Name: running
      - "tag:Environment": absent
      - "tag:AppId": absent
      - or:
        - "tag:OwnerContact": absent
        - "tag:DeptID": absent
    actions:
      - type: mark-for-op
        op: stop
        days: 4


Given that, you can run cloud-custodian with::

  # Validate the configuration (note this happens by default on run)
  $ custodian validate policy.yml

  # Dryrun on the policies (no actions executed) to see what resources
  # match each policy.
  $ custodian run --dryrun -s out policy.yml

  # Run the policy
  $ custodian run -s out policy.yml


Custodian supports a few other useful subcommands and options, including
outputs to s3, cloud watch metrics, sts role assumption. Policies go together
like lego bricks with actions and filters.

Consult the documentation for additional information, or reach out on gitter.

Get Involved
############

Mailing List - https://groups.google.com/forum/#!forum/cloud-custodian

Gitter - https://gitter.im/capitalone/cloud-custodian


Contributors
############

We welcome Your interest in Capital One’s Open Source Projects (the
“Project”). Any Contributor to the Project must accept and sign an
Agreement indicating agreement to the license terms below. Except for
the license granted in this Agreement to Capital One and to recipients
of software distributed by Capital One, You reserve all right, title,
and interest in and to Your Contributions; this Agreement does not
impact Your rights to use Your own Contributions for any other purpose.

`Sign the Individual Agreement <https://docs.google.com/forms/d/19LpBBjykHPox18vrZvBbZUcK6gQTj7qv1O5hCduAZFU/viewform>`_

`Sign the Corporate Agreement <https://docs.google.com/forms/d/e/1FAIpQLSeAbobIPLCVZD_ccgtMWBDAcN68oqbAJBQyDTSAQ1AkYuCp_g/viewform?usp=send_form>`_


Code of Conduct
###############

This project adheres to the `Open Code of Conduct <http://www.capitalone.io/codeofconduct/>`_. By participating, you are
expected to honor this code.
