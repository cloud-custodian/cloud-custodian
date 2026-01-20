# c7n-org: Multi Account Custodian Execution

% [comment]: # (         !!! IMPORTANT !!!                    )
% [comment]: # (This file is moved during document generation.)
% [comment]: # (Only edit the original document at ./tools/c7n_org/README.md)

c7n-org is a tool to run Custodian against multiple AWS accounts,
Azure subscriptions, GCP projects, or OCI tenancies in parallel.

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
  run         run a custodian policy across accounts (AWS, Azure, GCP, OCI)
  run-script  run a script across AWS accounts
  validate    validate policy files without requiring cloud credentials
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
  vars:
    charge_code: xyz
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

Example OCI Config File:

```yaml
tenancies:
- name: dev-tenancy
  profile: DEVTENANCY
  regions:
    - us-ashburn-1
    - us-phoenix-1
  vars:
    environment: dev
  tags:  
    - type:test
...

```

### Config File Generation

We also distribute scripts to generate the necessary config file in the [`scripts` folder](https://github.com/cloud-custodian/cloud-custodian/tree/main/tools/c7n_org/scripts).

**Note:** Currently these are distributed only via git. Per
<https://github.com/cloud-custodian/cloud-custodian/issues/2420>, we'll
be looking to incorporate them into a new c7n-org subcommand.

- For **AWS**, the script `orgaccounts.py` generates a config file
  from the AWS Organizations API.

```shell
python orgaccounts.py -f accounts.yml
```

- For **Azure**, the script `azuresubs.py` generates a config file
  from the Azure Resource Management API.

    - Please see the [Additional Azure Instructions](#additional-azure-instructions) for initial setup and other important info.

```shell
python azuresubs.py -f subscriptions.yml
```

- For **GCP**, the script `gcpprojects.py` generates a config file from
  the GCP Resource Management API.

```shell
python gcpprojects.py -f projects.yml
```

- For **OCI**, the script `ocitenancies.py` generates a config file
  using OCI Configuration file and OCI Organizations API.
  
    - Please refer to the [Additional OCI Instructions](#additional-oci-instructions) for additional information.

```shell
python ocitenancies.py -f tenancies.yml
```

## Running a Policy with c7n-org

To run a policy, the following arguments must be passed in:

```shell
-c | accounts|projects|subscriptions|tenancies config file
-s | output directory
-u | policy
```

For example:

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

## Selecting accounts, regions, policies for execution

You can filter the accounts to be run against by either passing the
account name or id via the `-a` flag, which can be specified multiple
times, or alternatively with comma separated values.

Groups of accounts can also be selected for execution by specifying
the `-t` tag filter.  Account tags are specified in the config
file. Given the above accounts config file, you can specify all prod
accounts with `-t type:prod`. You can specify the `-t` flag multiple
times or use a comma separated list.

You can specify which policies to use for execution by either
specifying `-p` or selecting groups of policies via their tags with
`-l`. Both options support being specified multiple times or using
comma separated values.

By default in AWS, c7n-org will execute in parallel across regions.
The `-r` flag can be specified multiple times and defaults to
`(us-east-1, us-west-2)`.  A special value of `all` will execute across
all regions.


See `c7n-org run --help` for more information.

## Defining and using variables

Each account/subscription/project configuration in the config file can
also define a variables section `vars` that can be used in policies'
definitions and are interpolated at execution time. These are in
addition to the default runtime variables custodian provides like
`account_id`, `now`, and `region`.

Example of defining in c7n-org config file:

```yaml
accounts:
- account_id: '123123123123'
  name: account-1
  role: arn:aws:iam::123123123123:role/CloudCustodian
  vars:
    charge_code: xyz
```

Example of using in a policy file:

```yaml
policies:
 - name: ec2-check-tag
   resource: aws.ec2
   filters:
      - "tag:CostCenter": "{charge_code}"
```

Another enhancement for `c7n-org run-script` is to support a few vars in the script arg.
The available vars are `account`, `account_id`, `region` and `output_dir`.

```shell
c7n-org run-script -s . -c my-projects.yml "./gcp_check_{region}.sh"
# or
c7n-org run-script -s . -c my-projects.yml './use_another_policy_result.sh "{output_dir}"'
```

**Note:** Variable interpolation is sensitive to proper quoting and spacing,
i.e., `{ charge_code }` would be invalid due to the extra white space. Additionally,
yaml parsing can transform a value like `{charge_code}` to null, unless it's quoted
in strings like the above example. Values that do interpolation into other content
don't require quoting, i.e., "my_{charge_code}".

## Validating Policies

c7n-org supports validating policy files without requiring cloud credentials.
This is useful for pre-commit checks and CI/CD pipelines.

```shell
c7n-org validate -c accounts.yml -u policies.yml
```

By default, validation performs schema checks, policy structure validation,
and detects common errors. The `--per-account` flag enables deeper validation
with account-specific variable expansion:

```shell
c7n-org validate -c accounts.yml -u policies.yml --per-account
```

In per-account mode, c7n-org validates that policy variables can be expanded
correctly for each account, catching issues like missing variable definitions
that would only appear at runtime.

You can filter which policies and accounts to validate using the same flags
as the `run` command:

- Filter policies with `-p`, `-l`, or `--resource`
- Filter accounts with `-a`, `--tags`, or `--not-accounts` (when using `--per-account`)
- Check for deprecated features with `--check-deprecations`

See `c7n-org validate --help` for more information.

## Other commands

c7n-org also supports running arbitrary scripts against accounts via
the run-script command.  For AWS the standard AWS SDK credential
information is exported into the process environment before executing.
For Azure and GCP, only the environment variables
`AZURE_SUBSCRIPTION_ID` and `PROJECT_ID` are exported(in addition of
the system env variables).

c7n-org also supports generating reports for a given policy execution
across accounts via the `c7n-org report` subcommand. By default,
account_id is not exposed to the output, but you may append it by
using `--field AccountID=account_id` in the cli.

## Additional Azure Instructions

If you're using an Azure Service Principal for executing c7n-org
you'll need to ensure that the principal has access to multiple
subscriptions.

For instructions on creating a service principal and granting access
across subscriptions, visit the [Azure authentication docs
page](https://cloudcustodian.io/docs/azure/authentication.html).

## Additional OCI Instructions

The script `ocitenancies.py` accepts an optional argument `--add-child-tenancies`
which adds all the child tenancies associated with the `DEFAULT` profile's tenancy 
in the generated c7n-org configuration file. If the profile for child tenancy is not available in 
the OCI configuration file, then either user can add the profile for the child tenancy to the
OCI configuration file and replace the `<ADD_PROFILE>` entry in the c7n-org configuration with the
corresponding profile name or the user can delete the child tenancy entry from the
c7n-org configuration file. For more info about config file, refer to this [page](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm).

If the user wants to query for the resources in the specific compartments in c7n-org, then the user
can pass the compartment OCID's to the `oci_compartments` under the `vars` section like below. If the 
`oci_comparments` is not passed under `vars`, then the resources will be fetched from the tenancy level.

```yaml
tenancies:
- name: dev-tenancy
  profile: DEVTENANCY
  regions:
    - us-ashburn-1
    - us-phoenix-1
  vars:
    oci_compartments: ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-2-Value,ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-3-Value
    environment: dev
- name: test-tenancy
  profile: TESTTENANCY
  regions:
    - us-ashburn-1
  vars:
    environment: test

```




