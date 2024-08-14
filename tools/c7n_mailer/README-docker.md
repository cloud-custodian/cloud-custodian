
# Cloud Custodian Mailer

The Cloud Custodian [`c7n_mailer`](https://github.com/cloud-custodian/cloud-custodian/tree/master/tools/c7n_mailer) is a simple tool for sending notifications with [Cloud Custodian](https://github.com/cloud-custodian/cloud-custodian). This image allows you to run the `c7n_mailer` purely in a Docker container, avoiding the need to install Python requirements.

# How to use this image

The basic command *without Docker* is:

```console
$ c7n-mailer --update-lambda -c /tmp/mailer.yaml
```

So all we need to do is:

* Map a volume for the `mailer.yaml`
* Make sure we pass AWS credentials

## Run c7n-mailer

This single command passes both `~/.aws` and environment variables for AWS credentials. You can pick one or the other, but it's just convenient to pass both.

```console
$ docker run --rm --env AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN --env AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION --env AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID --env AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY -v ~/.aws:/root/.aws -v /tmp:/tmp cloudcustodian/mailer:latest --update-lambda -c /tmp/mailer.yaml
```

> NOTE: The path doesn't have to be `/tmp`. That's just an example. Just replace `/tmp` with your actual path in `-v /tmp:/tmp`.
