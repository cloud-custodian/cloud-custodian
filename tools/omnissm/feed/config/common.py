# Copyright 2018 Capital One Services, LLC
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


import hashlib
import logging
import os

from dateutil.parser import parse as parse_date

log = logging.getLogger('omnissm.subscriber')


REGISTRATIONS_TABLE = os.environ.get('REGISTRATIONS_TABLE', 'omnissm-registrations')
RESOURCE_TAGS = set([n.strip() for n in os.environ.get(
    'RESOURCE_TAGS', 'App,OwnerContact,Name').split(',')])


class ManagedInstance(object):

    def __init__(self, ssm, db):
        self.ssm = ssm
        self.db = db

    @staticmethod
    def get_identity(account_id, resource_id):
        return hashlib.sha1(
            "%s-%s" % (account_id, resource_id)).hexdigest()

    def update(self, registration, cfg):
        tags, cloud_info = self.get_metadata(cfg)

        # Capturing tag metadata allow us to group and target
        log.info("Associating tags to %s tags:%s", registration["ManagedId"], tags)
        self.ssm.add_tags_to_resource(
            ResourceType='ManagedInstance',
            ResourceId=registration["ManagedId"],
            Tags=[{'Key': k, 'Value': v} for k, v in tags.items()])

        log.info(
            "Associating cloud inventory to %s info:\n%s",
            registration["ManagedId"], cloud_info)

        self.ssm.put_inventory(
            InstanceId=registration["ManagedId"],
            Items=[{
                "TypeName": "Custom:CloudInfo",
                "SchemaVersion": "1.0",
                "CaptureTime": parse_date(
                    cfg['configurationItemCaptureTime']).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Content": [cloud_info]}])

    def delete(self, registration):
        self.ssm.deregister_managed_instance(InstanceId=registration["ManagedId"])

    def get_registration(self, identity):
        # If we don't have any metadata on the item, bail, nothing to enrich
        # note this also implies we need to stream process the table changes.
        result = self.db.get_item(
            TableName=REGISTRATIONS_TABLE, Key={'id': {'S': identity}})
        if not result.get('Item'):
            log.warning("Instance not found %s", identity)
            return

        return {k: list(v.values())[0] for k, v in result['Item'].items()}

    def get_metadata(self, cfg):
        instance = cfg['configuration']
        tags = {}
        for t in RESOURCE_TAGS:
            if t in cfg['tags']:
                tags[t] = cfg['tags'][t]

        md = {
            "Region": cfg['awsRegion'],
            "AccountId": cfg['awsAccountId'],
            "Created": cfg['resourceCreationTime'],
            "InstanceId": cfg['resourceId'],
            "InstanceType": instance['instanceType'],
            "InstanceRole": instance.get(
                'iamInstanceProfile', {}).get('arn', ""),
            "VpcId": instance['vpcId'],
            "ImageId": instance['imageId'],
            "KeyName": instance.get('keyName', ""),
            "SubnetId": instance['subnetId'],
            "Platform": instance.get('platform') or 'Linux',
            'State': instance.get('state', {}).get('name'),
            # Private ip info picked up by network information
            # "SecurityGroups": [s['groupId'] for s in instance.get('securityGroups', [])],
            # Max length is 4096, use filtered tag set from above
        }

        for k, v in tags.items():
            md[k] = v

        # Tag with some generics for association activation based on tag values
        tags.update({
            'AccountId': cfg['awsAccountId'],
            'Cloud': 'AWS',
            'Platform': instance.get('platform') or 'Linux',
            'VpcId': instance['vpcId'],
            'InstanceId': cfg['resourceId'],
            'Name': tags.get('Name', cfg['resourceId'])
        })

        return tags, md
