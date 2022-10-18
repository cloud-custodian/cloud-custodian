# Custodian policies for Infrastructure Code


This package allows cloud custodian to evaluate policies directly
against infrastructure as code source assets.

It also provides a separate cli for better command line ux for
source asset evaluation.

# Install

We currently only support python 3.10 on mac and linux. We plan to
expand support for additional operating systems and python versions
over time.


```shell
pip install c7n_left
```

# Usage

```shell
$ c7n-left run --help

Usage: c7n-left run [OPTIONS]

  evaluate policies against iac sources

Options:
  --format TEXT
  -p, --policy-dir PATH
  -d, --directory PATH
  -o, --output [cli|github|json]
  --output-file FILENAME
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


# Outputs

if your using this in github actions, we have special output mode
for reporting annotations directly into the ui.

