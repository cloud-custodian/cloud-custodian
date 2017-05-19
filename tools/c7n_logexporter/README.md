# Cloud watch log exporter

A small serverless app to archive cloud logs across accounts to an archive bucket. It utilizes
cloud log export to s3 feature.

*Note* - For most folks, this functionality would be better achieved using a kinesis
stream hooked up to kinesis firehose to archive to s3, which would allow for streaming
archiving.


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
   See http://goo.gl/ for details.
 - Default periodicity for log group archival into s3 is daily.
 - Exporter is run with account credentials that have access to the archive s3 bucket.
 - Catch up archiving is not run in lambda (do a cli run first)
 - Lambda deployment only archives the last day periodically.


# Cli usage

```
make install
```

You can run on a single account / log group via the export subcommand
```
c7n-log-export export --help
```

## Config format

To ease usage when running across multiple accounts, a config file can be specified, as
an example.

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

## Multiple accounts via cli

To run on the cli across multiple accounts, edit the config.yml to specify multiple
accounts and log groups.

```
c7n-log-export run --config config.yml
```

# Serverless Usage

Edit config.yml to specify the accounts, archive bucket, and log groups you want to
use.

```
make install
make deploy
```

# TODO

- [ ] switch to structured logging

- [ ] finer grained periods?

- [ ] inner day runs

- [ ] cloud watch metrics stats on log groups?

- [ ] reason on overlapped dates (ie export till current time, need to pickup remainder of the day)

  update current time from the time of the last export, prefix metadata to bucket?

  each export task creates a structure under the day, for last write, we annotate to the s3 key.


# SAM issue on tracing as func property