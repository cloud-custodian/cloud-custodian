# c7n-trailcreator:  Retroactive Resource Creator Tagging

This script will process cloudtrail records to create a sqlite db of
resources and their creators, and then use that sqlitedb to tag
the resources with their creator's name.

In processing cloudtrail it can use either Athena or S3 Select. A
config file of the events and resources of interest is required.

## Install

```shell
$ pip install c7n-trailcreator

$ c7n-trailcreator --help
```

## Config File

The config file format here is similar to what custodian requires
for lambda policies on cloudtrail api events as an event selector.

First for each resource, the custodian resource-type is required
to be specified, and then for each event, we need to know the
name of the service, the event name, and a jmespath expression
to get the resource ids.

Here's a few examples, covering iam-user, iam-role, and an s3 bucket.


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

## Athena Usage

Trail creators supports loading data from s3 using s3 select or from cloudtrail s3 using athena.

Note you'll have to pre-create the athena table for cloudtrail per
[https://docs.aws.amazon.com/athena/latest/ug/cloudtrail-logs.html](https://docs.aws.amazon.com/athena/latest/ug/cloudtrail-logs.html)

Let's use the example config file to load up data for all the roles, buckets, and users created in 2019

```
c7n-trailcreator load-athena \
    --region us-east-1 \
	--resource-map resource_map.json \
	--table cloudtrail_logs_custodian_skunk_trails \
	--db "creators.db" \
	--year 2019
```

By default we'll use the default s3 athena output used by the console,
and the default db and primary workgroup, you can pass all of these in
on the cli to be more explicit.

You can also specify to just process a month with `--month 2019/11` or
an individual day with `--day 2019/02/01`

```
INFO:c7n_trailowner:Athena query:569712dc-d1e9-4474-b86f-6579c53b5b46
INFO:c7n_trailowner:Polling athena query progress scanned:489.24 Mb qexec:28.62s
INFO:c7n_trailowner:Polling athena query progress scanned:1.29 Gb qexec:88.96s
INFO:c7n_trailowner:Polling athena query progress scanned:2.17 Gb qexec:141.16s
INFO:c7n_trailowner:processing athena result page 78 records
INFO:c7n_trailowner:Athena Processed 78 records
```

Note you can reprocess a completed query's results, by passing in `--query-id` on the cli.

## Tagging

It supports this across all the resources that custodian supports.

```
$ c7n-trailcreator tag \
	--db creators.db \
	--creator-tag Owner \
	--region us-east-1
INFO:c7n_trailowner:account:644160558196 region:us-east-1 tag 13 iam-role resources users:5 population:97 not-found:84 records:124
INFO:c7n_trailowner:account:644160558196 region:us-east-1 tag 5 iam-user resources users:4 population:6 not-found:1 records:18
INFO:c7n_trailowner:account:644160558196 region:us-east-1 tag 9 s3 resources users:4 population:14 not-found:5 records:20
INFO:c7n_trailowner:auto tag summary account:644160558196 region:us-east-1
 iam-role-not-found: 84
 iam-role: 13
 iam-user-not-found: 1
 iam-user: 5
 s3-not-found: 5
 s3: 9
INFO:c7n_trailowner:Total resources tagged: 27
```

let's break down one of these log messages

```
INFO:c7n_trailowner:account:644160558196 region:us-east-1 tag 13 iam-role resources users:5 population:97 not-found:84 records:124
```

- records: the count of database create events we have for this resource type.
- users: the number of unique users for whom we have create events.
- not-found: the number of resources for which we do not have create events, i.e. created before or after our trail analysis period.
- population: the total number of resources in the account region.

## Multi Account / Multi Region

c7n-trailcreator supports executing across multiple accounts and regions when tagging
using the same file format that c7n-org uses to denote accounts. See `tag-org` subcommand.

