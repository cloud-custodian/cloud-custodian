# Copyright 2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from botocore.exceptions import ClientError
from c7n.actions import ActionRegistry, BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import (
    get_account_id,
    local_session,
    type_schema,
)

actions = ActionRegistry('cloudtrail.actions')


@resources.register('cloudtrail')
class CloudTrail(QueryResourceManager):
    action_registry = actions

    class resource_type(object):
        service = 'cloudtrail'
        enum_spec = ('describe_trails', 'trailList', None)
        #
        #detail_spec = (
        #    'get_event_selectors', 'TrailName', 'TrailArn', None)
        filter_name = 'trailNameList'
        filter_type = 'list'
        id = 'TrailArn'
        name = 'Name'
        dimension = None
        config_type = "AWS::CloudTrail::Trail"


def cloudtrail_policy(original, bucket_name, account_id):
    '''add CloudTrail permissions to an S3 policy, preserving existing'''
    ct_actions = [
        {
            'Action': 's3:GetBucketAcl',
            'Effect': 'Allow',
            'Principal': {'Service': 'cloudtrail.amazonaws.com'},
            'Resource': 'arn:aws:s3:::' + bucket_name,
            'Sid': 'AWSCloudTrailAclCheck20150319',
        },
        {
            'Action': 's3:PutObject',
            'Condition': {
                'StringEquals':
                {'s3:x-amz-acl': 'bucket-owner-full-control'},
            },
            'Effect': 'Allow',
            'Principal': {'Service': 'cloudtrail.amazonaws.com'},
            'Resource': 'arn:aws:s3:::%s/AWSLogs/%s/*' % (
                bucket_name, account_id
            ),
            'Sid': 'AWSCloudTrailWrite20150319',
        },
    ]
    # parse original policy
    if original is None:
        policy = {
            'Statement': [],
            'Version': '2012-10-17',
        }
    else:
        policy = json.loads(original['Policy'])
    original_actions = [a.get('Action') for a in policy['Statement']]
    for cta in ct_actions:
        if cta['Action'] not in original_actions:
            policy['Statement'].append(cta)
    return json.dumps(policy)


@actions.register('enable')
class EnableTrail(BaseAction):
    """Enables logging on the trail(s) named in the policy

    :Example:

    .. code-block: yaml

        policies:
          - name: trail-test
            description: Ensure CloudTrail logging is enabled
            resource: cloudtrail
            actions:
              - type: enable
                trail: mytrail
                bucket: trails
    """

    permissions = (
        'cloudtrail:CreateTrail',
        'cloudtrail:GetTrailStatus',
        'cloudtrail:StartLogging',
        'cloudtrail:UpdateTrail',
        's3:CreateBucket',
        's3:GetBucketPolicy',
        's3:PutBucketPolicy',
    )
    schema = type_schema(
        'enable',
        **{
            'trail': {'type': 'string'},
            'bucket': {'type': 'string'},
            'multi-region': {'type': 'boolean'},
            'global-events': {'type': 'boolean'},
            'notify': {'type': 'string'},
            'file-digest': {'type': 'boolean'},
            'kms': {'type': 'boolean'},
            'kms-key': {'type': 'string'},
            'required': ('bucket',),
        }
    )

    def process(self, trails):
        """Create or enable CloudTrail"""
        session = local_session(self.manager.session_factory)
        client = session.client('cloudtrail')
        bucket_name = self.data['bucket']
        trail_name = self.data.get('trail', 'default-trail')
        multi_region = self.data.get('multi-region', True)
        global_events = self.data.get('global-events', True)
        notify = self.data.get('notify', '')
        file_digest = self.data.get('file-digest', False)
        kms = self.data.get('kms', False)
        kms_key = self.data.get('kms-key', '')

        s3client = session.client('s3')
        s3client.create_bucket(Bucket=bucket_name)
        try:
            current_policy = s3client.get_bucket_policy(Bucket=bucket_name)
        except ClientError:
            current_policy = None
        account_id = get_account_id(session)
        policy_json = cloudtrail_policy(
            current_policy, bucket_name, account_id
        )
        s3client.put_bucket_policy(Bucket=bucket_name, Policy=policy_json)
        if trail_name not in [t.get('Name') for t in trails]:
            new_trail = client.create_trail(
                Name=trail_name,
                S3BucketName=bucket_name,
            )
            if new_trail:
                trails.append(new_trail)
                # the loop below will configure the new trail
        for trail in trails:
            if trail.get('Name') != trail_name:
                continue
            # enable
            arn = trail['TrailARN']
            status = client.get_trail_status(Name=arn)
            if not status['IsLogging']:
                client.start_logging(Name=arn)
            # apply configuration changes (if any)
            update_args = {}
            if multi_region != trail.get('IsMultiRegionTrail'):
                update_args['IsMultiRegionTrail'] = multi_region
            if global_events != trail.get('IncludeGlobalServiceEvents'):
                update_args['IncludeGlobalServiceEvents'] = global_events
            if notify != trail.get('SNSTopicArn'):
                update_args['SnsTopicName'] = notify
            if file_digest != trail.get('LogFileValidationEnabled'):
                update_args['EnableLogFileValidation'] = file_digest
            if kms_key != trail.get('KmsKeyId'):
                if not kms and 'KmsKeyId' in trail:
                    kms_key = ''
                update_args['KmsKeyId'] = kms_key
            if update_args:
                update_args['Name'] = trail_name
                client.update_trail(**update_args)
