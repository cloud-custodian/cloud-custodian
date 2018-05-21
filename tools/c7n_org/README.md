## What is c7n-org?

c7n-org is a tool to run custodian against multiple AWS accounts or Azure subscriptions at once.

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
  run         run a custodian policy across accounts (AWS or Azure)
  run-script  run a script across AWS accounts
```

In order to run c7n-org against multiple accounts, a config file must first be created containing pertinent information about the accounts:


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

### Config File Generation

We also distribute scripts to generate the necessary config file.

- For **AWS**, the script `orgaccounts.py` generates a config file from the AWS Organizations API
- For **Azure**, the script `azuresubs.py` generates a config file from the Azure Resource Management API
    - Please see the **Additional Azure Instructions** section at the bottom of the page for initial setup
    
```shell
python orgaccounts.py -f output.yml
```
```shell
python azuresubs.py -f output.yml
```

## Running a Policy with c7n-org

To run a policy, the following arguments must be passed in:

```shell
-c | accounts config file
-s | output directory
-u | policy
```


```shell
c7n-org run -c custodian-all-us.yml -s output -u test.yml --dryrun
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

## Selecting accounts and policy for execution

You can filter the accounts to be run against by either passing the account name or id
via the `-a` flag, which can be specified multiple times.

Groups of accounts can also be selected for execution by specifying the `-t` tag filter.
Account tags are specified in the config file. ie given the above accounts config file
you can specify all prod accounts with `-t type:prod`.

You can specify which policies to use for execution by either specifying `-p` or selecting
groups of policies via their tags with `-l`.


See `c7n-org run --help` for more information.

## Other commands

c7n-org also supports running arbitrary scripts on AWS against accounts via the run-script command, which
exports standard AWS SDK credential information into the process environment before executing.

c7n-org also supports generating reports for a given policy execution across accounts via
the `c7n-org report` subcommand.

## Additional Azure Instructions

In order for Cloud Custodian to have access to your subscription, permission must be 
given to the service principal through the Azure portal. 

For instructions on creating a service principal, visit the 
[Authentication docs page](http://capitalone.github.io/cloud-custodian/docs/azure/authentication.html).

Once the service principal is created, follow these steps:

- Open the `Subscriptions` tab
- Select a subscription you'd like to manage with Cloud Custodian
- Click `Access Control (IAM)`
- Click `Add`
- Set Role to `Contributor`
- Type name of service principal in search bar and select it
- Click `Save`

Now when you run `azuresubs.py` with the appropriate environment variables 
(see [auth docs](http://capitalone.github.io/cloud-custodian/docs/azure/authentication.html) 
if you are unclear on what those are), the subscription will be automatically included in the generated
config file.
