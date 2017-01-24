
# Custodian Sentry Integration

Generic Cloud Watch Logs scanner/subscription that
searches for tracebacks, extracts frames, and posts
to sentry.

Useful for any python code logging to cloud watch logs
including lambdas.


# Install

```
(cloud-custodian) $ pip install tools/c7n_sentry
[...]
(cloud-custodian) $ c7n-sentry
usage: c7n-sentry [-h] [--verbose] {deploy,orgreplay} ...
c7n-sentry: error: too few arguments
(cloud-custodian) $
```

You can use `c7n-sentry orgreplay` from your laptop or a cron job to replay
logs and send exceptions to Sentry.

```
(cloud-custodian) $ export SENTRY_DSN=foo
(cloud-custodian) $ export SENTRY_TOKEN=deadbeef
(cloud-custodian) $ c7n-sentry orgreplay -c config.json --sentry-org=yours
```

You can use `c7n-sentry deploy` to install a Lambda function that will
log exceptions to Sentry as they occur.

```
(cloud-custodian) $ export SENTRY_DSN=foo
(cloud-custodian) $ c7n-sentry deploy -c config.json --sentry-org=yours
```

Either way, `config.json` looks something like this:

```json
{
    "": {
        "name": "your-aws-account-name",
        "account_id": "0123456789",
        "config_files": {
            "": {
                "policies": [
                    {
                        "mode": "must by non-empty, but value is arbitrary",
                        "name": "foo"
                    }
                ]
            }
        },
        "role": "arn:aws:iam::123456789012:required/for/realtime"
    }
}
```

Both `name` and `account_id` refer to your AWS account. The crucial bit is
`name` under `policies`: we are going to look for a Lambda named
`custodian-foo` and replay the CloudWatch logs for that Lambda, sending any
Python exceptions we discover over to Sentry.
