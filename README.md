[![License](https://img.shields.io/badge/license-Apache%202-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

<!-- markdown-toc start - Don't edit this section. Run M-x markdown-toc-generate-toc again -->
**Table of Contents**
 - [Cloud Custodian](#cloud-custodian)
 - [Links](#links)
 - [Usage](#usage)
 - [Get Involved](#get-involved)

<!-- markdown-toc end -->

# Cloud Custodian

[![Join the chat at https://gitter.im/capitalone/cloud-custodian](https://badges.gitter.im/capitalone/cloud-custodian.svg)](https://gitter.im/capitalone/cloud-custodian?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

Cloud Custodian is a rules engine for AWS resource management. It
allows users to define policies to be enforced to enable a well
managed cloud, with metrics and structured outputs. It consolidates
many of the adhoc scripts organizations have into a lightweight
and flexible tool.

Organizations can use Custodian to manage their AWS environments by
ensuring compliance to security policies, tag policies, garbage
collection of unused resources, and cost management via off-hours
resource management.

Custodian policies are written in simple YAML configuration files that
specify given a resource type (ec2, asg, redshift, etc) and are
constructed from a vocabulary of filters and actions. Custodian was
created to unify the dozens of tools and scripts most organizations
use for managing their AWS accounts into one open source tool and
provide unified operations and reporting.

It integrates with lambda and cloudwatch events to provide for
realtime enforcement of policies with builtin provisioning, or can
isomorphically be used to query and operate against all of account
resources.


## Links

- [Docs](http://www.capitalone.io/cloud-custodian/)
- [Developer Install](http://www.capitalone.io/cloud-custodian/quickstart/developer.html)


## Usage

First a policy file needs to be created in yaml format, as an example:


```yaml

policies:
 - name: remediate-extant-keys
   description: |
     Scan through all s3 buckets in an account and ensure all objects
     are encrypted (default to AES256).  
   resources: s3
   actions:
     - encrypt-keys

 - name: ec2-require-non-public-and-encrypted-volumes
   resource: ec2 
   description: |
     Provision a lambda and cloud watch event target
     that looks at all new instances not in an autoscale group
     and terminates those with unencrypted volumes.
   mode:
     type: cloudtrail	
     events:
  	  - RunInstances
   filters:
     - Encrypted: false
   actions:
     - terminate

 - name: tag-compliance
   resources: ec2
   description:
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

Given that, you can run cloud-custodian 

```shell
  # Directory for outputs
  $ mkdir out

  # Validate the configuration
  $ custodian validate -c policy.yml

  # Dryrun on the policies (no actions executed)
  $ custodian run --dryrun -c policy.yml -s out

  # Run the policy 
  $ custodian run -c policy.yml -s out
```
  
Custodian supports a few other useful subcommands and options, including
outputs to s3, cloud watch metrics, sts role assumption.


Consult the documentation for additional information.

## Get Involved

Mailing List - https://groups.google.com/forum/#!forum/cloud-custodian

Irc - #cloud-custodian on irc.freenode.net

### Contributors

We welcome Your interest in Capital One’s Open Source Projects (the
“Project”). Any Contributor to the Project must accept and sign an
Agreement indicating agreement to the license terms below. Except for
the license granted in this Agreement to Capital One and to recipients
of software distributed by Capital One, You reserve all right, title,
and interest in and to Your Contributions; this Agreement does not
impact Your rights to use Your own Contributions for any other purpose

##### [Link to Agreement] (https://docs.google.com/forms/d/19LpBBjykHPox18vrZvBbZUcK6gQTj7qv1O5hCduAZFU/viewform)

This project adheres to the
[Open Code of Conduct][code-of-conduct]. By participating, you are
expected to honor this code.

[code-of-conduct]: http://www.capitalone.io/codeofconduct/
