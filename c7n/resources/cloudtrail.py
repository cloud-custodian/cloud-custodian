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


policy_json_tmpl = u'''{{
  "Version": "2012-10-17",
  "Statement": [
    {{
      "Sid": "AWSCloudTrailAclCheck20150319",
      "Effect": "Allow",
      "Principal": {{
        "Service": "cloudtrail.amazonaws.com"
      }},
      "Action": "s3:GetBucketAcl",
      "Resource": "arn:aws:s3:::{bucket_name}"
    }},
    {{
      "Sid": "AWSCloudTrailWrite20150319",
      "Effect": "Allow",
      "Principal": {{
        "Service": "cloudtrail.amazonaws.com"
      }},
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::{bucket_name}/AWSLogs/{account_id}/*",
      "Condition": {{
        "StringEquals": {{
          "s3:x-amz-acl": "bucket-owner-full-control"
        }}
      }}
    }}
  ]
}}'''


@actions.register('enable')
class EnableTrail(BaseAction):

    schema = type_schema(
        'enable',
        trails={'type': 'array', 'items': {'type': 'string'}},
        required=('trails',),
    )

    def process(self, trails):
        """Create or enable CloudTrail"""
        session = local_session(self.manager.session_factory)
        client = session.client('cloudtrail')
        existing = {t.get('Name') for t in trails}
        requested = set(self.data.get('trails'))
        to_create = requested.difference(existing)
        to_enable = requested.intersection(existing)
        for trail in trails:
            if trail.get('Name') in to_enable:
                # enable known trails if disabled
                arn = trail['TrailARN']
                status = client.get_trail_status(Name=arn)
                if not status['IsLogging']:
                    client.start_logging(Name=arn)
        if len(to_create):
            account_id = get_account_id(session)
        else:
            account_id = ''
        for trail_name in to_create:
            # create a trail (and its bucket)
            bucket_name = '{}-trails'.format(trail_name)
            s3client = session.client('s3')
            s3client.create_bucket(Bucket=bucket_name)
            policy_json = policy_json_tmpl.format(
                bucket_name=bucket_name, account_id=account_id,
            )
            s3client.put_bucket_policy(Bucket=bucket_name, Policy=policy_json)
            new_trail = client.create_trail(
                Name=trail_name,
                S3BucketName=bucket_name,
            )
            if new_trail:
                client.start_logging(Name=trail_name)
