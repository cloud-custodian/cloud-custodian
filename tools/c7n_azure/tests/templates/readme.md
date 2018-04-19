Test Template Provisioning
==========================

These templates will allow you to provision real Azure resources appropriate for recreating the VCR
cassettes used by the unit tests.  They will let you run the unit tests against real resources.

This directory contains two scripts `provision.sh` and `cleanup.sh` to provision and delete resources.

These scripts will provision or delete all ARM templates (`.json files`) in this directory using resource groups named
after the template files (`test_<filename>`).

This scripts Azure CLI, so you need to `az login` and `az account set -s 'subscription name'` first.

You can optionally pass a list of file names without extension to the scripts to act only on those templates:

```
$ provision.sh vm storage
$ cleanup.sh storage
```

or do everything

```
$ provision.sh
```

