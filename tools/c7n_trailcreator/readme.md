# c7n-trailcreator:  Retroactive Resource Creator Tagging

This script will process cloudtrail records to create a sqlite db of
resources and their creators, and then use that sqlitedb to tag
the resources with their creator's name.

In processing cloudtrail it can use either Athena or S3 Select. A
config file of the events and resources of interest is required.

## Install

```shell
$ pip install c7n_trailcreator

$ c7n-trailcreator --help
```

## Config File

The config file format here is similiar to what custodian requires
for lambda policies on cloudtrail api events as an event selector.

First for each resource, the custodian resource-type is required
to be specified, and then for each event, we need to know the
name of the service, the event name, and a jmespath expression
to get the resource ids.

Here's a a few examples, covering iam-user, iam-role, and and an s3 bucket.


```json
{
  "resources": [
    {
      "resource": "iam-role",
      "events": [
        {
          "event": "CreateRole",
          "ids": "requestParameters.roleName",
          "service": "iam.amazonaws.com"
        }
      ]
    },
    {
      "resource": "s3",
      "events": [
        {
          "ids": "requestParameters.bucketName",
          "event": "CreateBucket",
          "service": "s3.amazonaws.com"
        }
      ]
    },
    {
      "resource": "iam-user",
      "events": [
        {
          "event": "CreateUser",
          "ids": "requestParameters.userName",
          "service": "iam.amazonaws.com"
        }
      ]
    }]
}
```


## Tagging

It supports this across all the resources that custodian supports.


## Multi Account / Multi Region

c7n-trailcreator supports executing across multiple accounts and regions when tagging
using the same file format that c7n-org uses to denote accounts.

