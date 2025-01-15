# Custodian policies for Infrastructure Code


This package allows cloud custodian to evaluate policies directly
against infrastructure as code source assets.

It also provides a separate cli for better command line ux for
source asset evaluation.

## Install

We currently only support python > 3.10 on mac and linux, to run on windows
we recommend using our docker images.

```shell
pip install c7n-left
```

We also provide signed docker images. These images are built on top of chainguard's [wolfi linux
distribution](https://www.chainguard.dev/unchained/introducing-wolfi-the-first-linux-un-distro) which
is designed to be minimal, auditable, and secure.

```shell
docker pull cloudcustodian/c7n-left:dev
```

Images signatures can be verified using [cosign](https://github.com/sigstore/cosign)

```
export IMAGE=$(docker image inspect cloudcustodian/c7n-left:dev -f '{{index .RepoDigests 0}}')
cosign verify $IMAGE \
   --certificate-identity 'https://github.com/cloud-custodian/cloud-custodian/.github/workflows/docker.yml@refs/heads/main' \
   --certificate-oidc-issuer 'https://token.actions.githubusercontent.com'
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
  --filters TEXT                  Filter policies or resources as k=v pairs
                                  with globbing
  --warn-on TEXT                  Select policies to log instead of fail on
                                  via k=v pairs with globbing								  
  -p, --policy-dir PATH           Directory with policies
  -d, --directory PATH            IaC directory to evaluate
  -o, --output [cli|github|json]  Output format (default cli)
  --output-file FILENAME          Output file (default stdout)
  --var-file FILE                 Load variables from the given file, can be
                                  used more than once
  --output-query TEXT             Use a jmespath expression to filter json
                                  output
  --summary [policy|resource]
  --help                          Show this message and exit.
```


We'll create an empty directory with a policy in it

```yaml
policies:
  - name: test
    resource: terraform.aws_s3_bucket
    metadata:
      severity: medium
    filters:
      - server_side_encryption_configuration: absent
```

And now we can use it to evaluate a terraform root module

```shell

❯ c7n-left run -p policies -d module
Running 1 policies on 1 resources
test - terraform.aws_s3_bucket
  Failed
  File: s3.tf:1-8
  1 resource "aws_s3_bucket" "example" {                                                                                
  2   bucket = "my-custodian-test-bucket"                                                                               
  3   acl    = "private"                                                                                                
  4                                                                                                                     
  5   tags = {                                                                                                          
  6     original-tag = "original-value"                                                                                 
  7   }                                                                                                                 
  8 }                                                                                                                   

Evaluation complete 0.00 seconds -> 1 Failures
           Summary - By Policy           
┏━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
┃ Severity ┃ Policy ┃ Result            ┃
┡━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ medium   │ test   │ 1 failed 0 passed │
└──────────┴────────┴───────────────────┘
0 compliant of 1 total, 1 resource has 1 policy violation
```

For running in docker, you'll need to use volume mounts to provide access to 
the policy directory and terraform root module.

```shell
docker run -ti --rm -v $(pwd)/policies:/policies -v $(pwd)/root-module:/module \
       cloudcustodian/c7n-left:dev run -p /policies -d /module
```

If the terraform root module has other remote module dependencies, you'll need to fetch those first using terraform
before running c7n-left.

```shell
terraform get -update
```

## CLI Filters

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
    resource: [terraform.aws_ebs_volume, terraform.aws_sqs_queue]
    metadata:
      category: [encryption, security]
      severity: high
    filters:
       - kms_master_key_id: absent
```


## Outputs

if your using this in github actions, we have special output mode for
reporting annotations directly into pull requests with `--output
github`

We also display a summary output after displaying resource matches,
there are two summary displays available, the default policy summary,
and a resource summary which can be enabled via `--summary resource`.

By default any policy matches cause a run to exit code 1 to mark failure,
this behavior can be controlled via the `--warn-on` cli flag. ie. given a policy
with

```yaml
policies:
  - name: check-encryption
    resource: [terraform.aws_ebs_volume, terraform.aws_sqs_queue]
    metadata:
      category: [beta, security]
      severity: high
```

running the policy with `--warn-on category=beta` will cause matches to be logged only instead
of causing an exit code 1.


## Policy Language

Standard Custodian filters ([value](https://cloudcustodian.io/docs/filters.html#value-filter), [list-item](https://cloudcustodian.io/docs/aws/resources/aws-common-filters.html#aws-common-filters-list-item), `and`, `or`, `not`, [`reduce`](https://cloudcustodian.io/docs/filters.html#reduce-filter) and `event`) are available

Policies for c7n-left support a few additional capabilities beyond what's common for custodian policies.


Policies can be specified against multiple resource types either as an array or glob.

```yaml
policies:
  - name: check-encryption
    resource: [aws_ebs_volume, aws_sqs_queue]
```

### taggable filter

A `taggable` filter is available that allows filtering to only resources that support tagging.

In combination with resource wild card support, this allows using a single policy to enforce
an organization's tag standards.

```yaml
policies:
 - name: check-tag-policy
   resource: "terraform.aws*"
   filters:
     - taggable
     - or:
       - tag:Env: absent
       - tag:Owner: absent
       - tag:App: absent
```

This filter supports resources from several terraform providers including aws, azure, gcp, oci, tencentcloud.

terraform providers that support default_tags have those values automatically available on the applicable resources.

### traverse filter

A `traverse` filter is available that allows for multi-hop graph traversal from a resource
to any related resource.

ie, here's a policy against an aws ec2 instance, that checks if any of the security
groups attached to the instance, have a permission defined that allows access from
0.0.0.0/0

```yaml
policies:
 - name: check-security-group-open-cidr
   resource: terraform.aws_instance
   description: "EC2 should not be open to world on ssh"
   filters:
     - type: traverse
       resources:
         - aws_security_group
         - aws_security_ingress_permission
       attrs:
         - Ipv4: 0.0.0.0/0
```

### terraform data resources

Policies can also be written against data resources, note data
resources are prefixed with `data.`.

```yaml
policies:
 - name: check-ami-data
   resource: terraform.data.aws_ami
   filters:
     - type: value
       key: owners
       op: contains
       value: "099720109477"  # Canonical/ubuntu
```

and you can `traverse` from a resource to its data usage as well.

```yaml
policies:
 - name: check-owner-specified
   resource: terraform.aws_instance
   filters:
    - type: traverse
      resources: data.aws_ami
      attrs:
       - owners: present
```


### environment variables

c7n-left is typically run in CI systems, which provide a wealth
of information in environment variables. Policies can make use
of these environment variables in two different ways.

They can be used to interpolate the content of a policy, where they
will they will be substituted prior to the policy execution. Note this
uses python's [format capabilties](https://pyformat.info)

```yaml
policies:
 - name: "check-{env[REPO]}-{env[PR_NUMBER]}"
   resource: terraform.aws*
```

Additionally they can be evaluated by the policy using the `event` filter

```yaml
policies:
  - name: check-aws
    resource: terraform.aws*
    filters:
      - type: event
        key: env.REPO
        value: "cloud-custodian/cloud-custodian"
```

### jmespath
Sometimes you may have JSON encoded strings as part of your terraform.  For
example if you're working with an AWS ECS Task Definition the
`container_defintions` key will be a string and not a proper object.  You
may want to have a policy that prevents environment variables like `JWT_TOKEN`
or `DATABASE_PASSWORD` from being passed in because you should be using the
`secrets` parameter instead.

You can do this with the following filter:

```yaml
policies:
  - name: ecs-task-definition-with-plaintext-password
    description: >
      It's not recommended to use plaintext environment variables for sensitive
      information, such as credential data. Pass them through the `secrets`
      parameter instead.
    resource: terraform.aws_ecs_task_definition
    metadata:
      severity: High
      category: Encryption
      provider: aws
    filters:
      - container_definitions: not-null
      - type: list-item
        key: from_json(container_definitions)[].environment[]
        attrs:
          - type: value
            key: name
            op: regex
            value: '(?:.|\n)*(password|secret|token|key)'
```

The key here is teh `from_json` call to convert it from a string to an object.

## Policy Testing

c7n-left supports writing and running tests for policies.

To create a test for a policy, create a tests directory next to your policy files.

Within that tests directory, create a sub directory with the policy name.

Next add terraform files to this sub directory. Typically you would add
both terraform files that would match the policy and those that should not.

Finally you add assertions in a `left.plan[.yaml|.json]` file. The
format of the file is an array of dictionaries. The dictionaries are
used to match against the policy findings. The data its matching
against is what is found by using `c7n-left run --output json`. Each
key/value pair in the dictionary is matched against the finding.

So putting it all together, we've setup our tests as follows

```shell
❯ tree policy-dir-a/
policy-dir-a/
├── alb.yaml
└── tests
    └── alb-deletion-protection-disabled
        ├── left.plan.yaml
        ├── negative1.tf
        └── positive1.tf

3 directories, 4 files

❯ cat policy-dir-a/alb.yaml
policies:
  - name: alb-deletion-protection-disabled
    resource: [terraform.aws_lb, terraform.aws_alb]
    description: |
      Application Load Balancer should have deletion protection enabled
    metadata:
      severity: low
      category: "Insecure Configurations"
    filters:
      - enable_deletion_protection: empty

❯ cat policy-dir-a/tests/alb-deletion-protection-disabled/left.plan.yaml
- "resource.__tfmeta.filename": "positive1.tf"

```

and now we can run a test

```shell
❯ c7n-left test -p policy-dir-a/
Discovered 1 Tests
Failure alb-deletion-protection-disabled [{'resource.__tfmeta.filename':
'positive1.tf'}] checks not used

1 Test Complete (0.05s) 1 Failure
```

A test fails if either an assertion in the plan file does not match one policy finding, or if a policy finding is not matched by an assertion.
