# Ops Tools

## mugc

mugc (mu garbage collection) is a utility used to clean up Cloud
Custodian Lambda policies that are deployed in an AWS
environment. mugc finds and deletes extant resources based on the
prefix of the lambda name (default: `custodian-`).

### mugc Usage

By default mugc will inspect the lambda functions in the account and
compare to the policy files passed in. Any functions which begin with
the custodian prefix, but do not correspond to policies in the files
will be deleted. Use the `--dryrun` argument to preview the functions
which will be deleted.

This behavior, ie. target policies not found in the current set of
policy files, can be inverted so that mugc will instead only delete
extant policy resources for policies that are present in the set of
config files by using the the `--present` flag.

The only required argument is `-c`: a list of config (policy) files.

```
$ python tools/ops/mugc.py -c policies.yml
```

An example policy file.

```
policies:
  - name: delete
    resource: ebs
```

If you want to delete a specific Lambda Function you can use either
the `--prefix` argument or `--policy-regex` argument with the full
name of the function.

**TIP: Launch always before --dryrun command**

mugc also suports the following args:

```
usage: mugc.py [-h] [-c [CONFIG_FILES [CONFIG_FILES ...]]] [--present]
               [-r REGION] [--dryrun] [--profile PROFILE] [--prefix PREFIX]
               [--policy-regex POLICY_REGEX] [-p POLICY_FILTER]
               [--assume ASSUME_ROLE] [-v]
               [configs [configs ...]]

positional arguments:
  configs               Policy configuration file(s)

optional arguments:
  -h, --help            show this help message and exit
  -c [CONFIG_FILES [CONFIG_FILES ...]], --config [CONFIG_FILES [CONFIG_FILES ...]]
                        Policy configuration files(s)
  --present             Target policies present in config files for removal
                        instead of skipping them.
  -r REGION, --region REGION
                        AWS Region to target. Can be used multiple times, also
                        supports `all`
  --dryrun
  --profile PROFILE     AWS Account Config File Profile to utilize
  --prefix PREFIX       The Lambda name prefix to use for clean-up
  --policy-regex POLICY_REGEX
                        The policy must match the regex
  -p POLICY_FILTER, --policies POLICY_FILTER
                        Only use named/matched policies
  --assume ASSUME_ROLE  Role to assume
  -v                    toggle verbose logging

```

### mugc Usage with c7n-org

In order to use mugc in conjunction with c7n-org to cleanup policies in multiple accounts within a single run, it must be ran with `run-script`. Below is an example of how to run it against a single account in a single region utilizing the c7n-org configuration file.

```shell
$ c7n-org run-script -r us-east-1 -s output-dir -c config.yaml -a account-name "/path/to/python mugc.py -c policies.yaml --dryrun"
```
