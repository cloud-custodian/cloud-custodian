# Custodian Mailer

A mailer implementation for Custodian. Outbound mail delivery is still somewhat
organization-specific, so this at the moment serves primarily as an example
implementation.


## Email Message Relay

Custodian Mailer subscribes to an SQS queue, looks up users, and sends email
via SES. Custodian lambda and instance policies can send to it. SQS queues
should be cross-account enabled for sending between accounts.


## Tutorial

Our goal in starting out with the Custodian mailer is to install the mailer,
and run a policy that triggers an email to your inbox.

1. [Install](#developer-install-os-x-el-capitan) the mailer on your laptop.
1. In your text editor, create a `mailer.yml` file to hold your mailer config.
1. In the AWS console, create a new standard SQS queue (quick create is fine).
   Copy the queue URL to `queue_url` in `mailer.yml`.
1. In AWS, locate or create a role that has read access to the queue. Grab the
   role ARN and set it as `role` in `mailer.yml`.
1. Make sure your email address is verified in SES, and set it as
   `from_address` in `mailer.yml`.

Your `mailer.yml` should now look something like this:

```yaml
queue_url: https://sqs.us-east-1.amazonaws.com/1234567890/c7n-mailer-test
role: arn:aws:iam::123456790:role/c7n-mailer-test
from_address: you@example.com
```

(Also set `region` if you are in a region other than `us-east-1`.)

Now let's make a Custodian policy to populate your mailer queue. Create a
`test-policy.yml` file with this content:

```yaml
policies:
  - name: c7n-mailer-test
    resource: sqs
    filters:
     - "tag:MailerTest": absent
    actions:
      - type: notify
        template: default
        subject: testing the c7n mailer
        to:
          - you@example.com
        transport:
          type: sqs
          queue: https://sqs.us-east-1.amazonaws.com/1234567890/c7n-mailer-test
```

Now run:

```
c7n-mailer -c mailer.yml && custodian run -c test-policy.yml -s .
```

You should see output similar to the following:

```
(env) $ c7n-mailer -c mailer.yml && custodian run -c test-policy.yml -s .
DEBUG:custodian.lambda:Created custodian lambda archive size: 3.01mb
2017-01-12 07:55:16,227: custodian.policy:INFO Running policy c7n-mailer-test resource: sqs region:default c7n:0.8.22.0
2017-01-12 07:55:16,229: custodian.policy:INFO policy: c7n-mailer-test resource:sqs has count:1 time:0.00
2017-01-12 07:55:18,017: custodian.actions:INFO sent message:dead-beef policy:c7n-mailer-test template:default count:1
2017-01-12 07:55:18,017: custodian.policy:INFO policy: c7n-mailer-test action: notify resources: 1 execution_time: 1.79
(env) $
```

Check the AWS console for a new Lambda named `cloud-custodian-mailer`. The
mailer runs every five minutes, so wait a bit and then look for an email in
your inbox. If it doesn't appear, look in the lambda's logs for debugging
information. If it does, congratulations! You are off and running with the
Custodian mailer.


## Usage & Configuration

Once [installed](#developer-install-os-x-el-capitan) you should have a
`c7n-mailer` executable on your path:

```
(env) $ c7n-mailer
usage: c7n-mailer [-h] -c CONFIG
c7n-mailer: error: argument -c/--config is required
(env) $
```

Fundamentally what `c7n-mailer` does is deploy a Lambda (using
[Mu](http://www.capitalone.io/cloud-custodian/docs/policy/mu.html)) based on
configuration you specify in a YAML file.  Here is [the
schema](./c7n_mailer/cli.py#L11-L41) to which the file must conform, here is
[an example config](./example.yml), and here is a description of the options:

| Required? | Key                  | Type             | Notes                               |
|:---------:|:---------------------|:-----------------|:------------------------------------|
| &#x2705;  | `queue_url`          | string           | the queue to listen to for messages |
| &#x2705;  | `from_address`       | string           | default from address                |
|           | `contact_tags`       | array of strings | tags that we should look at for address information |


#### Standard Lambda Function Config

| Required? | Key                  | Type             |
|:---------:|:---------------------|:-----------------|
|           | `memory`             | integer          |
|           | `region`             | string           |
| &#x2705;  | `role`               | string           |
|           | `security_groups`    | array of strings |
|           | `subnets`            | array of strings |
|           | `timeout`            | integer          |


#### Mailer Infrastructure Config

| Required? | Key                  | Type             | Notes                               |
|:---------:|:---------------------|:-----------------|:------------------------------------|
|           | `cache`              | string           | memcached for caching ldap lookups  |
|           | `cross_accounts`     | object           | account to assume back into for sending to SNS topics |
|           | `ldap_bind_dn`       | string           | ldap server for resolving users     |
|           | `ldap_bind_user`     | string           | ldap server for resolving users     |
|           | `ldap_bind_password` | string           | ldap server for resolving users     |
|           | `ldap_uri`           | string           | ldap server for resolving users     |


#### SDK Config

| Required? | Key                  | Type             | Notes                               |
|:---------:|:---------------------|:-----------------|:------------------------------------|
|           | `http_proxy`         | string           |                                     |
|           | `https_proxy`        | string           |                                     |
|           | `profile`            | string           |                                     |


## Configuring a policy to send email

Outbound email can be added to any policy by including the `notify` action.

```yaml

policies:
  - name: bad-apples
    resource: asg
    filters:
     - "tag:ASV": absent
    actions:
      - type: notify
        template: default
        subject: fix your tags
        to:
          - resource-owner
        transport:
          type: sqs
          queue: https://sqs.us-east-1.amazonaws.com/80101010101/cloud-custodian-message-relay
```

So breaking it down, you add an action of type `notify`. You can specify a
template that's used to format the email; customizing templates is described
[below](#writing-an-email-template).

The `to` list specifies the intended recipient for the email. You can specify
either an email address, an SNS topic, or a special value. The special values
are either

- `resource-owner`, in which case the email will be sent to the listed
  `OwnerContact` tag on the resource that matched the policy, or
- `event-owner` for push-based/realtime policies that will send to the user
  that was responsible for the underlying event.

Both of these special values are best effort, i.e., if no `OwnerContact` tag is
specified then `resource-owner` email will not be delivered, and in the case of
`event-owner` an instance role or system account will not result in an email.

For reference purposes, the JSON Schema of the `notify` action:

```json
{
  "type": "object",
  "required": ["type", "transport", "to"],
  "properties": {
    "type": {"enum": ["notify"]},
    "to": {"type": "array", "items": {"type": "string"}},
    "subject": {"type": "string"},
    "template": {"type": "string"},
    "transport": {
      "type": "object",
      "required": ["type", "queue"],
      "properties": {
        "queue": {"type": "string"},
        "region": {"type": "string"},
        "type": {"enum": ["sqs"]}
      }
    }
  }
}
```


## Writing an email template

Templates are authored in [jinja2](http://jinja.pocoo.org/docs/dev/templates/).
Drop a file with the `.j2` extension into the
[`msg-templates`](./msg-templates) directory, and send a pull request to this
repo. You can then reference it in the `notify` action as the `template`
variable by file name minus extension. Templates ending with `.html.j2` are
sent as HTML-formatted emails, all others are sent as plain text.

The following variables are available when rendering templates:

| variable | value |
|:----------|:-----------|
| `recipient` | email address |
| `resources` | list of resources that matched the policy filters |
| `event` | for CWE-push-based lambda policies, the event that triggered |
| `action` | `notify` action that generated this SQS message |
| `policy` | policy that triggered this notify action |
| `account` | short name of the aws account |

The following extra global functions are available:

| signature | behavior |
|:----------|:-----------|
| `format_struct(struct)` | pretty print a json structure |
| `resource_tag(resource, key)` | retrieve a tag value from a resource or return an empty string |
| `resource_owner(resource)` | retrieve the contact field value for a resource from tags, if not found returns `Unknown` |
| `format_resource(resource, resource_type)` | renders a one line summary of a resource |


## Developer Install (OS X El Capitan)

Clone the repository:
```
$ git clone https://github.com/capitalone/cloud-custodian
```
Install dependencies (with virtualenv):
```
$ virtualenv c7n_mailer
$ source c7n_mailer/bin/activate
$ cd c7n_mailer
$ pip install -r requirements.txt
```
Install the extensions:
```
python setup.py develop
```
