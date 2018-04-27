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

"""
Responsible for enrichment and deletion.
"""

import boto3
import json
import hashlib
import logging
import os

from dateutil.parser import parse as parse_date

logging.root.setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)
log = logging.getLogger('omnissm.subscribe.config')

ResourceTypes = set(('AWS::EC2::Instance',))
ResourceTags = set([n.strip() for n in os.environ.get(
    'RESOURCE_TAGS', 'App,OwnerContact,Name').split(',')])
RegistrationTable = os.environ.get('SSM_REGISTRATIONS_TABLE') or 'omnissm-registrations'
ResourceStatusTypes = set(('ResourceDeleted', 'ResourceDiscovered', 'OK'))


def validate_event(event):
    return event.get('detail', {}).get('configurationItem')


def get_metadata(cfg):

    instance = cfg['configuration']
    tags = {}
    for t in ResourceTags:
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
        "KeyName": instance['keyName'],
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
        'Name': tags.get('Name', cfg['resourceId'])
    })

    return tags, md


def handle(event, context):
    log.info("Processing event\n %s", json.dumps(event, indent=2))

    msg = validate_event(event)
    if msg is None:
        return

    if msg['configurationItemStatus'] not in ResourceStatusTypes:
        return

    db = boto3.client('dynamodb', region_name=msg['awsRegion'])
    mid = get_instance_id(msg)

    print("Registration Check %s %s %s" % (
        RegistrationTable, msg['awsRegion'], mid))

    # If we don't have any metadata on the item, bail, nothing to enrich
    # note this also implies we need to stream process the table changes.
    result = db.get_item(
        TableName=RegistrationTable,
        Key={'id': {'S': mid}})
    if not result.get('Item'):
        log.info("Instance not found %s", mid)
        return

    registration = {k: list(v.values())[0] for k, v in result['Item'].items()}

    ssm = boto3.client('ssm', region_name=msg['awsRegion'])

    if msg['configurationItemStatus'] in ('ResourceDiscovered', 'OK'):
        log.info("Update/Add instance info %s", result['Item'])
        process_add_update(ssm, registration, msg)
    else:
        log.info("Delete instance %s", result['Item'])
        process_delete(ssm, registration, msg)


def process_delete(ssm, registration, msg):
    ssm.deregister_managed_instance(InstanceId=registration["ManagedId"])


def process_add_update(ssm, registration, msg):
    tags, cloud_info = get_metadata(msg)

    # Capturing tag metadata allow us to group and target
    log.info("associating tags to %s tags:%s", registration["ManagedId"], tags)
    ssm.add_tags_to_resource(
        ResourceType='ManagedInstance',
        ResourceId=registration["ManagedId"],
        Tags=[{'Key': k, 'Value': v} for k, v in tags.items()])

    log.info(
        "associating cloud inventory to %s info:\n%s",
        registration["ManagedId"], cloud_info)

    ssm.put_inventory(
        InstanceId=registration["ManagedId"],
        Items=[{
            "TypeName": "Custom:CloudInfo",
            "SchemaVersion": "1.0",
            "CaptureTime": parse_date(
                msg['configurationItemCaptureTime']).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Content": [cloud_info]}])


def get_instance_id(msg):
    return hashlib.sha1(
        "%s-%s" % (msg['awsAccountId'], msg['resourceId'])).hexdigest()


def unwrap(msg):
    data = None
    if 'Body' in msg:
        data = json.loads(msg['Body'])
    elif 'Message' in msg:
        data = json.loads(msg['Message'])
    else:
        raise ValueError("unknown msg: %s" % msg)

    if 'Message' in data:
        data = json.loads(data['Message'])

    return data
