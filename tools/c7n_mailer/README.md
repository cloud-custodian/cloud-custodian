# Custodian Mailer

A mailer implementation for custodian. Outbound mail delivery
is still somewhat organization specific, so this at the moment
serves primarily as an example implementation.

## Email Message Relay

Subscribes to sqs queue, lookups users, and sends email via ses.

Custodian lambda and instance policies can send to it, sqs queues
should be cross account enabled for sending between accounts.


## Configuring a policy to send email

Outbound email can be added to any policy by including the notify
action.

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

So breaking it down, you add an action of type notify. You can specify a template that's
used to format the email. Customizing templates is describe below.

The `to` list specifies the intendend recipient for the email. You can specify either
an email address, sns topic, or a special value. The special values are either
`resource-owner` in which case the email will be sent to the listed OwnerContact tag
on the resource that matched the policy, or `event-owner` for push based/real time policies
that will send to the user to the that was responsible for the underlying event. *Note*
both of these special values are best effort, ie. if no OwnerContact tag is specified
then `resource-owner` email will not be delivered, and in the case of `event-owner` an
instance role or system account will not result in an email.


For reference purposes the jsonschema of the notify action.

```

{
'type': 'object',
'required': ['type', 'transport', 'to'],
'properties': {
  'type': {'enum': ['notify']},
  'to': {'type': 'array', 'items': {'type': 'string'}},
  'subject': {'type': 'string'},
  'template': {'type': 'string'},
  'transport': {
   	  'type': 'object',
	  'required': ['type', 'queue'],
	  'properties': {
 	    'queue': {'type': 'string'},
		'region': {'type': 'string'},
		'type': {'enum': ['sqs']}}
		}
	}
}
```


## Writing an email template

Templates are authored in jinja2

http://jinja.pocoo.org/docs/dev/templates/

Drop a jinja2 template file with the .j2 extension into the
'msg-templates' directory, and send a pull request to this repo.

You can then reference it in the notify action as the `template`
variable by file name minus extension.

Templates ending with .html.j2 are sent as html formatted emails,
all others are sent as plain text.

The following variables are available when rendering templates

  - recipient : email address
  - resources : list of resources that matched the policy filters.
  - event : For cwe push based lambda policies, the event that triggered
  - action : The notify action that generated this sqs message.
  - policy : The policy that triggered this notify action.
  - account : Short name of the aws account.

The following extra global functions are available

  - format_struct : pretty print a json structure.
  - resource_tag(resource, key): retrieve a tag value from a resource or return an empty string
  - resource_owner(resource): retrieve the contact field value for a resource from tags, if not found returns Unknown
  - format_resource(resource, resource_type): renders a one line summary of a resource


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
