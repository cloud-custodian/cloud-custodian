# c7n-log-exporter: Cloud watch log exporter automation

A small serverless app to archive cloud logs across accounts to an archive bucket. It utilizes
cloud log export to s3 feature for historical exports.

It also supports kinesis streams / firehose to move to realtime exports in the same format
as the periodic historical exports.


## Features

 - Log group filtering by regex
 - Incremental support based on previously synced dates
 - Incremental support based on last log group write time
 - Cross account via sts role assume
 - Lambda and CLI support.
 - Day based log segmentation (output keys look
   like $prefix/$account_id/$group/$year/$month/$day/$export_task_uuid/$stream/$log)
 

## Assumptions

 - The archive bucket has already has appropriate bucket policy permissions.
   For details see:
   https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/S3ExportTasks.html#S3Permissions
 - Default periodicity for log group archival into s3 is daily.
 - Exporter is run with account credentials that have access to the archive s3 bucket.
 - Catch up archiving is not run in lambda (do a cli run first)


## Cli usage

```
make install
```

You can run on a single account / log group via the export subcommand
```
c7n-log-exporter export --help
```

## Config format

To ease usage when running across multiple accounts, a config file can be specified, as
an example.

### Using S3 Bucket as destination

```
destination:
  bucket: custodian-log-archive
  prefix: logs2

accounts:
  - name: custodian-demo
    role: "arn:aws:iam::111111111111:role/CloudCustodianRole"
    groups:
      - "/aws/lambda/*"
      - "vpc-flow-logs"
```

### Using CloudWatch Destination as destination cross account
The Cloudwatch Destination needs setup in account and access policy set on CloudWatch Destination to to allow 
source account access to the Cloudwatch Destination

```
subscription:
  destination-arn: "arn:aws:logs:us-east-1:111111111111:destination:CustodianCWLogsDestination"
  destination-role: "arn:aws:iam::111111111111:role/CWLtoKinesisRole"
  name: "CustodianCWLogsDestination"

destination:
  bucket: custodian-log-archive
  prefix: logs2

accounts:
  - name: custodian-demo
    # https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CreateSubscriptionFilter-IAMrole.html
    subscription-role: "arn:aws:iam::111111111111:role/<role-name>"
    role: "arn:aws:iam::111111111111:role/CloudCustodianRole"
    groups:
      - "/aws/lambda/*"
      - "vpc-flow-logs"
```

## Multiple accounts via cli

To run on the cli across multiple accounts, edit the config.yml to specify multiple
accounts and log groups.

```
c7n-log-exporter run --config config.yml
```

## Serverless Usage

Edit config.yml to specify the accounts, archive bucket, and log groups you want to
use.

```
make install
make deploy
```

