# Ops Tools

## mugc
mugc (mu garbage collection) is a utility used to clean up Cloud Custodian Lambda policies that are deployed in an AWS environment. mugc finds and deletes extant resources based on the prefix of the lambda name (default: `custodian-`).

By default, mugc excludes resources within specified config files.  If you would like to invert this behavior and target them instead, use the `--present` flag.

### mugc Usage

The only required argument is `-c`: a list of config (policy) files.

```
$ python tools/ops/mugc.py -c policies.yml
```

mugc also suports the following args:

```
usage: mugc.py [-h] -c CONFIG_FILES [-r REGION] [--dryrun] [--profile PROFILE]
               [--prefix PREFIX] [--present] [--policy-regex POLICY_REGEX] [--assume ASSUME_ROLE] [-v]
```
