# Cloud watch log exporter

A small serverless app to archive cloud logs across accounts to an archive bucket.

Default periodicity for archival into s3 is daily.

# Cli usage

```
make install
```

You can run on a single account / log group via the export subcommand
```
c7n-log-export export --help
```

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