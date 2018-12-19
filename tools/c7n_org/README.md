## What is c7n-org?

c7n-org is a tool to run custodian against multiple AWS accounts,
Azure subscriptions, or GCP projects in parallel.

## Installation

```shell
pip install c7n-org
```

c7n-org has 3 run modes:

```shell
Usage: c7n-org [OPTIONS] COMMAND [ARGS]...

  custodian organization multi-account runner.

Options:
  --help  Show this message and exit.

Commands:
  report      report on an AWS cross account policy execution
  run         run a custodian policy across accounts (AWS, Azure, GCP)
  run-script  run a script across AWS accounts
```

In order to run c7n-org against multiple accounts, a config file must
first be created containing pertinent information about the accounts:


Example AWS Config File:

```yaml
accounts:
- account_id: '123123123123'
  name: account-1
  regions:
  - us-east-1
  - us-west-2
  role: arn:aws:iam::123123123123:role/CloudCustodian
  tags:
  - type:prod
  - division:some division
  - partition:us
  - scope:pci
...
```

Example Azure Config File:

```yaml
subscriptions:
- name: Subscription-1
  subscription_id: a1b2c3d4-e5f6-g7h8i9...
- name: Subscription-2
  subscription_id: 1z2y3x4w-5v6u-7t8s9r...
```

Example GCP Config File:

```yaml
projects:
- name: app-dev
  project_id: app-203501
  tags:
  - label:env:dev  
- name: app-prod
  project_id: app-1291
  tags:
  - label:env:dev

```

### Config File Generation

We also distribute scripts to generate the necessary config file in the `scripts` folder.

**Note** Currently these are distributed only via git, per
https://github.com/capitalone/cloud-custodian/issues/2420 we'll
be looking to incorporate them into a new c7n-org subcommand.

- For **AWS**, the script `orgaccounts.py` generates a config file
  from the AWS Organizations API

- For **Azure**, the script `azuresubs.py` generates a config file
  from the Azure Resource Management API

    - Please see the [Additional Azure Instructions](#Additional-Azure-Instructions) 
    - for initial setup and other important info

- For **GCP**, the script `gcpprojects.py` generates a config file from
  the GCP Resource Management API


```shell
python orgaccounts.py -f accounts.yml
```
```shell
python azuresubs.py -f subscriptions.yml
```
```shell
python gcpprojects.py -f projects.yml
```

## Running a Policy with c7n-org

To run a policy, the following arguments must be passed in:

```shell
-c | accounts|projects|subscriptions config file
-s | output directory
-u | policy
```


```shell
c7n-org run -c accounts.yml -s output -u test.yml --dryrun
```

After running the above command, the following folder structure will be created:

```
output
    |_ account-1
        |_ us-east-1
            |_ policy-name
                |_ resources.json
                |_ custodian-run.log
        |_ us-west-2
            |_ policy-name
                |_ resources.json
                |_ custodian-run.log
    |- account-2
...
```

Use `c7n-org report` to generate a csv report from the output directory.

## Selecting accounts and policy for execution

You can filter the accounts to be run against by either passing the
account name or id via the `-a` flag, which can be specified multiple
times.

Groups of accounts can also be selected for execution by specifying
the `-t` tag filter.  Account tags are specified in the config
file. ie given the above accounts config file you can specify all prod
accounts with `-t type:prod`.

You can specify which policies to use for execution by either
specifying `-p` or selecting groups of policies via their tags with
`-l`.


See `c7n-org run --help` for more information.

## Other commands

c7n-org also supports running arbitrary scripts on AWS against
accounts via the run-script command, which exports standard AWS SDK
credential information into the process environment before executing.

c7n-org also supports generating reports for a given policy execution
across accounts via the `c7n-org report` subcommand.

## Additional Azure Instructions

If you're using an Azure Service Principal for executing c7n-org
you'll need to ensure that the principal has access to multiple
subscriptions.

For instructions on creating a service principal and granting access
across subscriptions, visit the [Azure authentication docs
page](http://capitalone.github.io/cloud-custodian/docs/azure/authentication.html).
