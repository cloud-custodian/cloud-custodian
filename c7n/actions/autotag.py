# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .core import EventAction
from c7n.exceptions import PolicyValidationError
from c7n.manager import resources
from c7n import utils


class AutoTagUser(EventAction):
    """Tag a resource with the user who created/modified it.

    .. code-block:: yaml

      policies:
        - name: ec2-auto-tag-ownercontact
          resource: ec2
          description: |
            Triggered when a new EC2 Instance is launched. Checks to see if
            it's missing the OwnerContact tag. If missing it gets created
            with the value of the ID of whomever called the RunInstances API
          mode:
            type: cloudtrail
            role: arn:aws:iam::123456789000:role/custodian-auto-tagger
            events:
              - RunInstances
          filters:
           - tag:OwnerContact: absent
          actions:
           - type: auto-tag-user
             tag: OwnerContact

    There's a number of caveats to usage. Resources which don't
    include tagging as part of their api may have some delay before
    automation kicks in to create a tag. Real world delay may be several
    minutes, with worst case into hours[0]. This creates a race condition
    between auto tagging and automation.

    In practice this window is on the order of a fraction of a second, as
    we fetch the resource and evaluate the presence of the tag before
    attempting to tag it.

    References

     CloudTrail User
     https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-user-identity.html
    """ # NOQA

    schema_alias = True
    schema = utils.type_schema(
        'auto-tag-user',
        required=['tag'],
        **{'user-type': {
            'type': 'array',
            'items': {'type': 'string',
                      'enum': [
                          'IAMUser',
                          'AssumedRole',
                          'FederatedUser'
                      ]}},
           'update': {'type': 'boolean'},
           'tag': {'type': 'string'},
           'principal_id_tag': {'type': 'string'},
           'value': {'type': 'string',
                     'enum': [
                         'userName',
                         'arn',
                         'sourceIPAddress',
                         'principalId'
                     ]},
           }
    )

    def get_permissions(self):
        return self.manager.action_registry.get(
            'tag')({}, self.manager).get_permissions()

    def validate(self):
        if self.manager.data.get('mode', {}).get('type') != 'cloudtrail':
            raise PolicyValidationError(
                "Auto tag owner requires an event %s" % (self.manager.data,))
        if self.manager.action_registry.get('tag') is None:
            raise PolicyValidationError(
                "Resource does not support tagging %s" % (self.manager.data,))
        if 'tag' not in self.data:
            raise PolicyValidationError(
                "auto-tag action requires 'tag'")
        return self

    def get_user_info_value(self, utype, event):
        value = None

        vtype = self.data.get('value', None)
        if vtype is None:
            return

        if vtype == "userName":
            if utype == "IAMUser":
                value = event['userIdentity'].get('userName', '')
            elif utype == "AssumedRole" or utype == "FederatedUser":
                value = event['userIdentity'].get('sessionContext', {}).get(
                    'sessionIssuer', {}).get('userName', '')
        elif vtype == "arn":
            value = event['userIdentity'].get('arn', '')
        elif vtype == "sourceIPAddress":
            value = event.get('sourceIPAddress', '')
        elif vtype == "principalId":
            value = event['userIdentity'].get('principalId', '')

        return value

    def get_tag_value(self, event):
        event = event['detail']
        utype = event['userIdentity']['type']
        if utype not in self.data.get('user-type', ['AssumedRole', 'IAMUser', 'FederatedUser']):
            return

        user = None
        if utype == "IAMUser":
            user = event['userIdentity']['userName']
            principal_id_value = event['userIdentity'].get('principalId', '')
        elif utype == "AssumedRole" or utype == "FederatedUser":
            user = event['userIdentity']['arn']
            _, user = user.rsplit('/', 1)
            principal_id_value = event['userIdentity'].get('principalId', '').split(':')[0]
            # instance role
            if user.startswith('i-'):
                return
            # lambda function (old style)
            elif user.startswith('awslambda'):
                return

        value = self.get_user_info_value(utype, event)

        # if the auto-tag-user policy set update to False (or it's unset) then we
        return {'user': user, 'id': principal_id_value, 'value': value}

    def process(self, resources, event):
        if event is None:
            return

        user_info = self.get_tag_value(event)
        if user_info is None:
            self.log.warning("user info not found in event")
            return

        # will skip writing their UserName tag and not overwrite pre-existing values
        if not self.data.get('update', False):
            untagged_resources = []
            # iterating over all the resources the user spun up in this event
            for resource in resources:
                tag_already_set = False
                for tag in resource.get('Tags', ()):
                    if tag['Key'] == self.data['tag']:
                        tag_already_set = True
                        break
                if not tag_already_set:
                    untagged_resources.append(resource)
        # if update is set to True, we will overwrite the userName tag even if
        # the user already set a value
        else:
            untagged_resources = resources

        new_tags = {}
        if user_info['value']:
            new_tags[self.data['tag']] = user_info['value']
        elif user_info['user']:
            new_tags[self.data['tag']] = user_info['user']

        # if principal_id_key is set (and value), we'll set the principalId tag.
        principal_id_key = self.data.get('principal_id_tag', None)
        if principal_id_key and user_info['id']:
            new_tags[principal_id_key] = user_info['id']

        if new_tags:
            self.set_resource_tags(new_tags, untagged_resources)
        return new_tags

    def set_resource_tags(self, tags, resources):
        tag_action = self.manager.action_registry.get('tag')
        for key, value in tags.items():
            tag_action({'key': key, 'value': value}, self.manager).process(resources)

    @classmethod
    def register_resource(cls, registry, resource_class):
        if 'auto-tag-user' in resource_class.action_registry:
            return
        if resource_class.action_registry.get('tag'):
            resource_class.action_registry.register('auto-tag-user', AutoTagUser)


resources.subscribe(AutoTagUser.register_resource)
