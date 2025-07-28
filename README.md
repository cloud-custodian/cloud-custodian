Cloud Custodian (c7n) - ManoMano Edition
========================================

<p align="center"><img src="https://cloudcustodian.io/img/logo_capone_devex_cloud_custodian.svg" alt="Cloud Custodian Logo" width="200px" height="200px" /></p>

---

[![slack](https://img.shields.io/badge/slack-chat-yellow)](https://communityinviter.com/apps/cloud-custodian/c7n-chat)
[![CI](https://github.com/cloud-custodian/cloud-custodian/workflows/CI/badge.svg?event=push)](https://github.com/cloud-custodian/cloud-custodian/actions?query=workflow%3ACI+branch%3Amaster+event%3Apush)
[![](https://img.shields.io/badge/license-Apache%202-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![](https://codecov.io/gh/cloud-custodian/cloud-custodian/branch/master/graph/badge.svg)](https://codecov.io/gh/cloud-custodian/cloud-custodian)
[![](https://requires.io/github/cloud-custodian/cloud-custodian/requirements.svg?branch=master)](https://requires.io/github/cloud-custodian/cloud-custodian/requirements/?branch=master)
[![CII Best Practices](https://bestpractices.coreinfrastructure.org/projects/3402/badge)](https://bestpractices.coreinfrastructure.org/projects/3402)

**Note:** This is a fork of Cloud Custodian maintained by ManoMano with custom modifications and enhancements specific to our infrastructure needs. See [CHANGELOG.md](CHANGELOG.md) for details on our additions.

Cloud Custodian, also known as c7n, is a rules engine for managing
public cloud accounts and resources. It allows users to define
policies to enable a well managed cloud infrastructure, that\'s both
secure and cost optimized. It consolidates many of the adhoc scripts
organizations have into a lightweight and flexible tool, with unified
metrics and reporting.

Custodian can be used to manage AWS, Azure, and GCP environments by
ensuring real time compliance to security policies (like encryption and
access requirements), tag policies, and cost management via garbage
collection of unused resources and off-hours resource management.

Custodian also supports running policies on infrastructure as code assets
to provide feedback directly on developer workstations or within CI pipelines.

Custodian policies are written in simple YAML configuration files that
enable users to specify policies on a resource type (EC2, ASG, Redshift,
CosmosDB, PubSub Topic) and are constructed from a vocabulary of filters
and actions.

It integrates with the cloud native serverless capabilities of each
provider to provide for real time enforcement of policies with builtin
provisioning. Or it can be run as a simple cron job on a server to
execute against large existing fleets.

Cloud Custodian is a CNCF Incubating project, lead by a community of hundreds
of contributors.

Features
--------

-   Comprehensive support for public cloud services and resources with a
    rich library of actions and filters to build policies with.
-   Run policies on infrastructure as code (terraform, etc) assets.	
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
-   [Project Roadmap](https://github.com/orgs/cloud-custodian/projects/1)
-   [Developer Install](https://cloudcustodian.io/docs/developer/installing.html)
-   [Presentations](https://www.google.com/search?q=cloud+custodian&source=lnms&tbm=vid)
-   [YouTube Channel](https://www.youtube.com/channel/UCdeXCdFLluylWnFfS0-jbDA)

Quick Install
-------------

Custodian is published on pypi as a series of packages with the `c7n`
prefix, its also available as a docker image.

### Using Poetry (Recommended for ManoMano fork)

```shell
$ poetry install
$ poetry shell
```

### Using pip

```shell
$ python3 -m venv custodian
$ source custodian/bin/activate
(custodian) $ pip install c7n
```

### Building and Pushing to ECR

This fork includes a `build-and-push.sh` script to build Docker images and push them to AWS ECR:

```shell
$ ./build-and-push.sh
```

This script builds the customized Cloud Custodian images and pushes them to the ManoMano ECR registry.


Usage
-----

The first step to using Cloud Custodian (c7n) is writing a YAML file
containing the policies that you want to run. Each policy specifies
the resource type that the policy will run on, a set of filters which
control resources will be affected by this policy, actions which the policy
with take on the matched resources, and a mode which controls which
how the policy will execute.

The best getting started guides are the cloud provider specific tutorials.

 - [AWS Getting Started](https://cloudcustodian.io/docs/aws/gettingstarted.html)
 - [Azure Getting Started](https://cloudcustodian.io/docs/azure/gettingstarted.html)
 - [GCP Getting Started](https://cloudcustodian.io/docs/gcp/gettingstarted.html)

As a quick walk through, below are some sample policies for AWS resources.

  1. will enforce that no S3 buckets have cross-account access enabled.
  1. will terminate any newly launched EC2 instance that do not have an encrypted EBS volume.
  1. will tag any EC2 instance that does not have the follow tags
     "Environment", "AppId", and either "OwnerContact" or "DeptID" to
     be stopped in four days.

```yaml
policies:
 - name: s3-cross-account
   description: |
     Checks S3 for buckets with cross-account access and
     removes the cross-account access.
   resource: aws.s3
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
     Schedule a resource that does not meet tag compliance policies to be stopped in four days. Note a separate policy using the`marked-for-op` filter is required to actually stop the instances after four days.
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

You can run Cloud Custodian via Docker as well:

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

$ docker run -it \
  -v $(pwd)/output:/home/custodian/output \
  -v $(pwd)/policy.yml:/home/custodian/policy.yml \
  -v $(cd ~ && pwd)/.aws/credentials:/home/custodian/.aws/credentials \
  -v $(cd ~ && pwd)/.aws/config:/home/custodian/.aws/config \
  --env-file <(env | grep "^AWS") \
  cloudcustodian/c7n run -v -s /home/custodian/output /home/custodian/policy.yml
```

The [custodian cask
tool](https://cloudcustodian.io/docs/tools/cask.html) is a go binary
that provides a transparent front end to docker that mirors the regular
custodian cli, but automatically takes care of mounting volumes.

Consult the documentation for additional information, or reach out on gitter.

Cloud Provider Specific Help
----------------------------

For specific instructions for AWS, Azure, and GCP, visit the relevant getting started page.

- [AWS](https://cloudcustodian.io/docs/aws/gettingstarted.html)
- [Azure](https://cloudcustodian.io/docs/azure/gettingstarted.html)
- [GCP](https://cloudcustodian.io/docs/gcp/gettingstarted.html)

Get Involved
------------

-   [GitHub](https://github.com/cloud-custodian/cloud-custodian) - (This page)
-   [Slack](https://communityinviter.com/apps/cloud-custodian/c7n-chat) - Real time chat if you're looking for help or interested in contributing to Custodian! 
    - [Gitter](https://gitter.im/cloud-custodian/cloud-custodian) - (Older real time chat, we're likely migrating away from this)
-   [Linen.dev](https://www.linen.dev/s/cloud-custodian/c/general) - Follow our discussions on Linen
-   [Mailing List](https://groups.google.com/forum/#!forum/cloud-custodian) - Our project mailing list, subscribe here for important project announcements, feel free to ask questions
-   [Reddit](https://reddit.com/r/cloudcustodian) - Our subreddit
-   [StackOverflow](https://stackoverflow.com/questions/tagged/cloudcustodian) - Q&A site for developers, we keep an eye on the `cloudcustodian` tag
-   [YouTube Channel](https://www.youtube.com/channel/UCdeXCdFLluylWnFfS0-jbDA/) - We're working on adding tutorials and other useful information, as well as meeting videos

Community Resources
-------------------

We have a regular community meeting that is open to all users and developers of every skill level.
Joining the [mailing list](https://groups.google.com/forum/#!forum/cloud-custodian) will automatically send you a meeting invite. 
See the notes below for more technical information on joining the meeting. 

- [Community Meeting Videos](https://www.youtube.com/watch?v=qy250y0UT-4&list=PLJ2Un8H_N5uBeAAWK95SnWvm_AuNJ8q2x)
- [Community Meeting Notes Archive](https://github.com/orgs/cloud-custodian/discussions/categories/announcements)
- [Upcoming Community Events](https://cloudcustodian.io/events/)
- [Cloud Custodian Annual Report 2021](https://github.com/cncf/toc/blob/main/reviews/2021-cloud-custodian-annual.md) - Annual health check provided to the CNCF outlining the health of the project
- [Ada Logics Third Party Security Audit](https://ostif.org/cc-audit-complete/)


Additional Tools
----------------

The Custodian project also develops and maintains a suite of additional
tools here
<https://github.com/cloud-custodian/cloud-custodian/tree/master/tools>:

- [**_Org_:**](https://cloudcustodian.io/docs/tools/c7n-org.html) Multi-account policy execution.

- [**_ShiftLeft_:**](https://cloudcustodian.io/docs/tools/c7n-left.html) Shift Left ~ run policies against Infrastructure as Code assets like terraform.

- [**_PolicyStream_:**](https://cloudcustodian.io/docs/tools/c7n-policystream.html) Git history as stream of logical policy changes.

- [**_Salactus_:**](https://cloudcustodian.io/docs/tools/c7n-salactus.html) Scale out s3 scanning.

- [**_Mailer_:**](https://cloudcustodian.io/docs/tools/c7n-mailer.html) A reference implementation of sending messages to users to notify them.

- [**_Trail Creator_:**](https://cloudcustodian.io/docs/tools/c7n-trailcreator.html) Retroactive tagging of resources creators from CloudTrail

- **_TrailDB_:** Cloudtrail indexing and time series generation for dashboarding.

- [**_LogExporter_:**](https://cloudcustodian.io/docs/tools/c7n-logexporter.html) Cloud watch log exporting to s3

- [**_Cask_:**](https://cloudcustodian.io/docs/tools/cask.html) Easy custodian exec via docker

- [**_Guardian_:**](https://cloudcustodian.io/docs/tools/c7n-guardian.html) Automated multi-account Guard Duty setup

- [**_Omni SSM_:**](https://cloudcustodian.io/docs/tools/omnissm.html) EC2 Systems Manager Automation

- [**_Mugc_:**](https://github.com/cloud-custodian/cloud-custodian/tree/master/tools/ops#mugc) A utility used to clean up Cloud Custodian Lambda policies that are deployed in an AWS environment.

Contributing
------------

See <https://cloudcustodian.io/docs/contribute.html>

Security
--------

If you've found a security related issue, a vulnerability, or a
potential vulnerability in Cloud Custodian please let the Cloud
[Custodian Security Team](mailto:security@cloudcustodian.io) know with
the details of the vulnerability. We'll send a confirmation email to
acknowledge your report, and we'll send an additional email when we've
identified the issue positively or negatively.

Code of Conduct
---------------

This project adheres to the [CNCF Code of Conduct](https://github.com/cncf/foundation/blob/master/code-of-conduct.md)

By participating, you are expected to honor this code.

