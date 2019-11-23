# Ops Tools

## mugc
mugc (mu garbage collection) is a utility used to clean up Cloud Custodian Lambda policies that are deployed in an AWS environment. mugc finds and deletes extant resources based on the prefix of the lambda name (default: `custodian-`).

### mugc Usage

The only required argument is `-c`: a list of config (policy) files.

```
$ python tools/ops/mugc.py -c policies.yml
```

The policy file must be like:

```
policies:
  - name: delete
    resource: ebs
```

If you want to delete a specific Lambda Function you must put `--prefix` argument.

**You can't choose which CloudCustodian lambda will be delete from the config policy passed as required argument**

**TIP: Launch always before --dryrun command**

mugc also suports the following args:

```
usage: mugc.py [-h] -c CONFIG_FILES [-r REGION] [--dryrun] [--profile PROFILE]
               [--prefix PREFIX] [--assume ASSUME_ROLE] [-v]
```
