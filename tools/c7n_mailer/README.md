# Custodian Mailer

A mailer implementation for Custodian. Outbound mail delivery is still somewhat
organization-specific, so this at the moment serves primarily as an example
implementation.


## Email Message Relay

Custodian Mailer subscribes to an SQS queue, looks up users, and sends email
via SES. Custodian lambda and instance policies can send to it. SQS queues
should be cross-account enabled for sending between accounts.


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
