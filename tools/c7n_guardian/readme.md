
# c7n-guardian: Automated multi-account Guard Duty setup

Amazon Guard Duty provides for machine learning based threat
intelligence and detection on resources in your aws accounts. This
project provides a cli tool for automating multi-account of aws guard
duty. Given a config file holding a set of account information, this
cli will setup one as a master account, and the remainder as member
accounts.

The following cli will enable guard duty on all accounts tagged
dev. The master guard duty account can be specified by name or account
id. Running enable multiple times will idempotently converge.

```shell
$ c7n-guardian enable --config accounts.yml --master 120312301231 --tags dev
```

The accounts config file is similiar to c7n-org, with the addition of the
account email.

```shell
$ cat accounts.yml

accounts:
  - name: guard-duty-master
    email: guard-duty-master@example.com
    account_id: "2020202020202"
    role: "arn:aws:iam::2020202020202:role/CustodianGuardDuty"
    tags:
      - prod

  - name: cicd
    email: cicd@example.com
    account_id: "1010101010101"
    role: "arn:aws:iam::1010101010101:role/CustodianGuardDuty"
    tags:
      - dev
      - cicd

```

The cli also has support for disabling and reporting on accounts

```shell
$ c7n-guardian --help
Usage: c7n-guardian [OPTIONS] COMMAND [ARGS]...

  Automate Guard Duty Setup.

Options:
  --help  Show this message and exit.

Commands:
  disable  suspend guard duty in the given accounts.
  enable   enable guard duty on a set of accounts
  report   report on guard duty enablement by account

```

## Accounts Credentials

The cli needs credentials access to assume the roles in the config
file for all accounts (master and members), the execution credentials
used can be sourced from a profile, or from role assumption in
addition to credential sourcing supported by the aws sdk.


## Using custodian policies for remediation

Here's some example policies that will provision a custodian lambda
that receives the guard duty notifications and performs some basic
remediation on the alerted resources, respectively stopping an ec2
instance, and removing an access key. You have the full access to
custodian's actions and filters for doing additional activities in
response to events.


```yaml
policies:

 - name: ec2-guard-remediate
   resource: ec2
   mode:
     role: arn:aws:iam::{account_id}:role/CustodianPolicyExecution
     type: guard-duty
   filters:
     # Filter for medium and high severity events
     - type: event
       key: detail.severity
       op: gte
       value: 4.5
   actions:
     - stop

 - name: iam-guard-remediate
   resource: iam-user
   mode:
     role: arn:aws:iam::{account_id}:role/CustodianPolicyExecution
     type: guard-duty
   filters:
     # Only a particular type of event, go ahead and remove keys
     - type: event
       key: detail.type
       value: "UnauthorizedAccess:IAMUser/TorIPCaller"
   actions:
     - remove-keys
```
