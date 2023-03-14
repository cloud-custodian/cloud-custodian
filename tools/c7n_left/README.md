# Custodian policies for Infrastructure Code


This package allows cloud custodian to evaluate policies directly
against infrastructure as code source assets.

It also provides a separate cli for better command line ux for
source asset evaluation.

## Install

We currently only support python 3.10 on mac and linux. We plan to
expand support for additional operating systems and python versions
over time.


```shell
pip install c7n_left
```

## Usage

```shell
❯ c7n-left run --help

Usage: c7n-left run [OPTIONS]

  evaluate policies against IaC sources.

  c7n-left -p policy_dir -d terraform_root --filters "severity=HIGH"

  WARNING - CLI interface subject to change.

Options:
  --format TEXT
  --filters TEXT                  filter policies or resources as k=v pairs
                                  with globbing
  -p, --policy-dir PATH
  -d, --directory PATH
  -o, --output [cli|github|json]
  --output-file FILENAME
  --output-query TEXT
  --summary [policy|resource]
  --help                          Show this message and exit.
```


We'll create an empty directory with a policy in it

```yaml
policies:
  - name: test
    resource: terraform.aws_s3_bucket
    filters:
      - server_side_encryption_configuration: absent
```

And now we can use it to evaluate a terraform root module

```shell
$ c7n-left run --policy-dir policies -d root_module
DEBUG:c7n.iac:Loaded 3 resources
Running 1 policies
DEBUG:c7n.iac:Filtered from 3 to 1 terraformresourcemanager
test - terraform.aws_s3_bucket
  Failed
  File: main.tf:25-28
  25 resource "aws_s3_bucket" "example_c" {  
  26   bucket = "c7n-aws-s3-encryption-audit-test-c"  
  27   acl    = "private"
  28 }

Execution complete 0.01 seconds
```


## Filters

Which policies and which resources are evaluated can be controlled via
command line via `--filters` option.

Available filters

- `name` - policy name
- `category` - policy category
- `severity` - minimum policy severity (unknown, low, medium, high, critical)
- `type` - resource type, ie. aws_security_group
- `id` - resource id  ie. aws_vpc.example 

Multiple values for a given filter can be specified as comma separate values, and all filters
except severity support globbing.

Examples
```
# run all encryption policies on ebs volumes and sqs queues
c7n-left run -p policy_dir -d terraform --filters="category=encryption type=aws_ebs_volume,aws_sqs_queue"

# run all medium and higher level policies cost policies
c7n-left run -p policy_dir -d terraform --filters="severity=medium category=cost"
```

policy values for severity and category are specified in its metadata section. ie

```yaml
policies:
  - name: check-encryption
    resource: [aws_ebs_volume, aws_sqs_queue]
    metadata:
      category: [encryption, security]
      severity: high
    filters:
       - kms_master_key_id: absent
```       


## Outputs

if your using this in github actions, we have special output mode
for reporting annotations directly into pull requests with `--output github`

We also display a summary output after displaying resource matches, there are
two summary displays available, the default policy summary, and a resource summary
which can be enabled via `--summary resource`.


