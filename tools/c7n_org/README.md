## What is c7n-org?

c7n-org is a tool to run custodian against multiple accounts at once.

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
  report      report on a cross account policy execution.
  run         run a custodian policy across accounts
  run-script  run an aws script across accounts
```

In order to run c7n-org against multiple accounts, a config file must first be created containing pertinent information about the accounts:

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
