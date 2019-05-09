Cloud Custodian
=================

<center><img src="https://cloudcustodian.io/img/logo_capone_devex_cloud_custodian.svg" alt="Cloud Custodian Logo" width="200px" height="200px" align_center/></center>

---

[![](https://badges.gitter.im/cloud-custodian/cloud-custodian.svg)](https://gitter.im/cloud-custodian/cloud-custodian?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![](https://dev.azure.com/cloud-custodian/cloud-custodian/_apis/build/status/cloud-custodian.cloud-custodian?branchName=master)](https://dev.azure.com/cloud-custodian/cloud-custodian/_build)
[![](https://img.shields.io/badge/license-Apache%202-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![](https://codecov.io/gh/cloud-custodian/cloud-custodian/branch/master/graph/badge.svg)](https://codecov.io/gh/cloud-custodian/cloud-custodian)
[![](https://requires.io/github/cloud-custodian/cloud-custodian/requirements.svg?branch=master)](https://requires.io/github/cloud-custodian/cloud-custodian/requirements/?branch=master)

Cloud Custodian is a rules engine for managing public cloud accounts and
resources. It allows users to define policies to enable a well managed
cloud infrastructure, that\'s both secure and cost optimized. It
consolidates many of the adhoc scripts organizations have into a
lightweight and flexible tool, with unified metrics and reporting.

Custodian can be used to manage AWS, Azure, and GCP environments by
ensuring real time compliance to security policies (like encryption and
access requirements), tag policies, and cost management via garbage
collection of unused resources and off-hours resource management.

Custodian policies are written in simple YAML configuration files that
enable users to specify policies on a resource type (EC2, ASG, Redshift,
CosmosDB, PubSub Topic) and are constructed from a vocabulary of filters
and actions.

It integrates with the cloud native serverless capabilities of each
provider to provide for real time enforcement of policies with builtin
provisioning. Or it can be run as a simple cron job on a server to
execute against large existing fleets.

"[Engineering the Next Generation of Cloud
Governance](https://cloudrumblings.io/cloud-adoption-engineering-the-next-generation-of-cloud-governance-21fb1a2eff60)"
by \@drewfirment

Features
--------

-   Comprehensive support for public cloud services and resources with a
    rich library of actions and filters to build policies with.
-   Supports arbitrary filtering on resources with nested boolean
    conditions.
-   Dry run any policy to see what it would do.
-   Automatically provisions serverless functions and event sources (
    AWS CloudWatchEvents, AWS Config Rules, Azure EventGrid, GCP
    AuditLog & Pub/Sub, etc)
-   Cloud provider native metrics outputs on resources that matched a
    policy
-   Structured outputs into cloud native object storage of which
    resources matched a policy.
-   Intelligent cache usage to minimize api calls.
-   Supports multi-account/subscription/project usage.
-   Battle-tested - in production on some very large cloud environments.

Links
-----

-   [Homepage](http://cloudcustodian.io)
-   [Docs](http://cloudcustodian.io/docs/index.html)
-   [Developer Install](https://cloudcustodian.io/docs/developer/installing.html)
-   [Presentations](https://www.google.com/search?q=cloud+custodian&source=lnms&tbm=vid)

Quick Install
-------------

```shell
$ python3 -m venv custodian
$ source custodian/bin/activate
(custodian) $ pip install c7n
```


Usage
-----

Cloud Custodian works on a YAML policy that are user generated. The policy 
contains the resources that the policy will run on, filters control which resources 
will be affected by this policy, modes control how the policy will execute, and actions 
are the actions the policy will take. Below is a sample policy that uses AWS and assumes that 
the user have the access necessary to preform the tasks. This policy ensures that these 3 rules are 
followed:
  1. will enforce that no S3 buckets have cross-account access enabled.
  1. will terminate any EC2 instance that do not have an encrypted EBS volume.
  1. will stop any EC2 instance that does not have the follow tags "Environment", "AppId", and either "OwnerContact" or "DeptID".

```yaml
policies:
- name: s3-cross-account
   description: |
     Checks S3 for buckets with cross-account access and
     removes the cross-account access.
   resource: s3
   region: us-east-1
   filters:
     - type: cross-account
   actions:
     - type: remove-statements
       statement_ids: matched

- name: ec2-require-non-public-and-encrypted-volumes
  resource: aws.ec2
  description: |
    Provision a lambda and cloud watch event target
    that looks at all new instances and terminates those with
    unencrypted volumes.
  mode:
    type: cloudtrail
    role: CloudCustodian-QuickStart
    events:
      - RunInstances
  filters:
    - type: ebs
      key: Encrypted
      value: false
  actions:
    - terminate

- name: tag-compliance
  resource: aws.ec2
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
```

You can validate, test, and run Cloud Custodian with the example policy with these commands:

```shell
# Validate the configuration (note this happens by default on run)
$ custodian validate policy.yml

# Dryrun on the policies (no actions executed) to see what resources
# match each policy.
$ custodian run --dryrun -s out policy.yml

# Run the policy
$ custodian run -s out policy.yml
```

You can run Cloud Custodian with a policy in Docker as well

```shell
# Download the image
$ docker pull cloudcustodian/c7n
$ mkdir output

# Run the policy
#
# This will run the policy using only the environment variables for authentication
$ docker run -it \
  -v $(pwd)/output:/home/custodian/output \
  -v $(pwd)/policy.yml:/home/custodian/policy.yml \
  --env-file <(env | grep "^AWS\|^AZURE\|^GOOGLE") \
  cloudcustodian/c7n run -v -s /home/custodian/output /home/custodian/policy.yml

# Run the policy (using AWS's generated credentials from STS)
#
# NOTE: We mount the ``.aws/credentials`` and ``.aws/config`` directories to
# the docker container to support authentication to AWS using the same credentials
# credentials that are available to the local user if authenticating with STS.
# This exposes your container to additional credentials than may be necessary,
# i.e. additional credentials may be available inside of the container than is
# minimally necessary.

$ docker run -it \
  -v $(pwd)/output:/home/custodian/output \
  -v $(pwd)/policy.yml:/home/custodian/policy.yml \
  -v $(cd ~ && pwd)/.aws/credentials/home/custodian/:.aws/credentials \
  -v $(cd ~ && pwd)/.aws/config:/home/custodian/.aws/config \
  --env-file <(env | grep "^AWS") \
  cloudcustodian/c7n run -v -s /home/custodian/output /home/custodian/policy.yml
```

Custodian supports other useful subcommands and options, including
outputs to S3, CloudWatch metrics, STS role assumption. Policies go
together like Lego bricks with actions and filters.

Consult the documentation for additional information, or reach out on gitter.

Cloud Provider Specific Help
----------------------------

For specific instructions for AWS, Azure, and GCP, visit the relevant getting started page.

- [AWS](https://cloudcustodian.io/docs/aws/gettingstarted.html)
- [Azure](https://cloudcustodian.io/docs/azure/gettingstarted.html)
- [GCP](https://cloudcustodian.io/docs/gcp/gettingstarted.html)

Get Involved
------------

-   [Reddit](https://reddit.com/r/cloudcustodian)
-   [Gitter](https://gitter.im/cloud-custodian/cloud-custodian)
-   [GitHub](https://github.com/cloud-custodian/cloud-custodian)
-   [Mailing List](https://groups.google.com/forum/#!forum/cloud-custodian)

Additional Tools
----------------

The Custodian project also develops and maintains a suite of additional
tools here
<https://github.com/cloud-custodian/cloud-custodian/tree/master/tools>:

- **_Org_:** Multi-account policy execution.

- **_PolicyStream_:** Git history as stream of logical policy changes.

- **_Salactus_:** Scale out s3 scanning.

- **_Mailer_:** A reference implementation of sending messages to users to notify them.

- **_TrailDB_:** Cloudtrail indexing and time series generation for dashboarding.

- **_LogExporter_:** Cloud watch log exporting to s3

- **_Index_:** Indexing of custodian metrics and outputs for dashboarding

- **_Sentry_:** Cloudwatch Log parsing for python tracebacks to integrate with
    <https://sentry.io/welcome/>

Contributors
------------

We welcome Your interest in Capital One's Open Source Projects (the
"Project"). Any Contributor to the Project must accept and sign an
Agreement indicating agreement to the license terms below. Except for
the license granted in this Agreement to Capital One and to recipients
of software distributed by Capital One, You reserve all right, title,
and interest in and to Your Contributions; this Agreement does not
impact Your rights to use Your own Contributions for any other purpose.

[Sign the Individual
Agreement](https://docs.google.com/forms/d/19LpBBjykHPox18vrZvBbZUcK6gQTj7qv1O5hCduAZFU/viewform)

[Sign the Corporate
Agreement](https://docs.google.com/forms/d/e/1FAIpQLSeAbobIPLCVZD_ccgtMWBDAcN68oqbAJBQyDTSAQ1AkYuCp_g/viewform?usp=send_form)

Code of Conduct
---------------

This project adheres to the [Open Code of Conduct](https://developer.capitalone.com/single/code-of-conduct/). By
participating, you are expected to honor this code.
