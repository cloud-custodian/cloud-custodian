# c7n-policystream: Policy Changes from Git

% [comment]: # (         !!! IMPORTANT !!!                    )
% [comment]: # (This file is moved during document generation.)
% [comment]: # (Only edit the original document at ./tools/c7n_policystream/README.md)

Using custodian in accordance with infrastructure as code principles,
we store policy assets in a versioned control repository. This
provides for an audit log and facilitates code reviews. However this
capability is primarily of use to humans making semantic interpretations
of changes.

This script also provides logical custodian policy changes over a git
repo and allows streaming those changes for machine readable/application
consumption. Its typically used as a basis for CI integrations or indexes
over policies.

Two example use cases:

  - Doing dryrun only on changed policies within a pull request
  - Constructing a database of policy changes.

Policystream works on individual github repositories, or per Github integration
across an organization's set of repositories.

## Install

policystream can be installed via pypi, provided the require pre-requisites
libraries are available (libgit2 > 0.26)

```
pip install c7n-policystream
```

Docker images available soon, see build for constructing your own.

## Build

Alternatively a docker image can be built as follows

```shell
# Note must be top level directory of checkout
cd cloud-custodian

docker build -t policystream:latest -f tools/c7n_policystream/Dockerfile .

docker run --mount src="$(pwd)",target=/repos,type=bind policystream:latest
```

## Usage

Streaming use case (default stream is to stdout, also supports kinesis, rdbms and sqs)

```
  $ c7n-policystream stream -r foo
  2018-08-12 12:37:00,567: c7n.policystream:INFO Cloning repository: foo
  <policy-add policy:foi provider:aws resource:ec2 date:2018-08-02T15:13:28-07:00 author:Kapil commit:09cb85>
  <policy-moved policy:foi provider:aws resource:ec2 date:2018-08-02T15:14:24-07:00 author:Kapil commit:76fce7>
  <policy-remove policy:foi provider:aws resource:ec2 date:2018-08-02T15:14:46-07:00 author:Kapil commit:570ca4>
  <policy-add policy:ec2-guard-duty provider:aws resource:ec2 date:2018-08-02T15:14:46-07:00 author:Kapil commit:570ca4>
  <policy-add policy:ec2-run provider:aws resource:ec2 date:2018-08-02T15:16:00-07:00 author:Kapil commit:d3d8d4>
  <policy-remove policy:ec2-run provider:aws resource:ec2 date:2018-08-02T15:18:31-07:00 author:Kapil commit:922c1a>
  <policy-modified policy:ec2-guard-duty provider:aws resource:ec2 date:2018-08-12T09:39:43-04:00 author:Kapil commit:189ea1>
  2018-08-12 12:37:01,275: c7n.policystream:INFO Streamed 7 policy changes
```

Policy diff between two source and target revision specs. If source
and target are not specified default revision selection is dependent
on current working tree branch. The intent is for two use cases, if on
a non-master branch then show the diff to master.  If on master show
the diff to previous commit on master. For repositories not using the
`master` convention, please specify explicit source and target.


```
  $ c7n-policystream diff -r foo -v
```

Pull request use, output policies changes between current branch and master.

```
  $ c7n-policystream diff -r foo
  policies:
  - filters:
    - {type: cross-account}
    name: lambda-access-check
    resource: aws.lambda
```

## Options

```
$ c7n-policystream --help
Usage: c7n-policystream [OPTIONS] COMMAND [ARGS]...

  Policy changes from git history

Options:
  --help  Show this message and exit.

Commands:
  diff          Policy diff between two arbitrary revisions.
  org-checkout  Checkout repositories from a GitHub organization.
  org-stream    Stream changes for repos in a GitHub organization.
  stream        Stream git history policy changes to destination.
```
