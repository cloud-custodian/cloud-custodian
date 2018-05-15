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

"""
Config event subscriber responsible for enrichment and deletion on ssm instances.
"""

import boto3
import json
import logging

from common import ManagedInstance

logging.root.setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)
log = logging.getLogger('omnissm.subscribe.config')

ResourceTypes = set(('AWS::EC2::Instance',))
ResourceStatusTypes = set(('ResourceDeleted', 'ResourceDiscovered', 'OK'))

ssm = boto3.client('ssm')
db = boto3.client('dynamodb')


def validate_event(event):
    if event.get('source', '') != "aws.config":
        return
    if event['detail']['configurationItem']['resourceType'] not in ResourceTypes:
        return
    if event['configurationItemStatus'] not in ResourceStatusTypes:
        return
    return event.get('detail', {}).get('configurationItem')


def handle(event, context):
    log.info("Processing event\n %s", json.dumps(event, indent=2))

    msg = validate_event(event)
    if msg is None:
        return

    mi = ManagedInstance(ssm, db)
    mid = mi.get_identity(msg['awsAccountId'], msg['resourceId'])

    # If we don't have any metadata on the item, bail, nothing to enrich
    # note this also implies we need to stream process the table changes.
    registration = mi.get_registration(mid)
    if registration is None:
        log.warning("Instance not found %s %s", mid, msg['awsAccountId'], msg['resourceId'])
        return

    if msg['configurationItemStatus'] in ('ResourceDiscovered', 'OK'):
        log.info("Update/Add instance info %s", registration)
        mi.update(registration, msg)
    else:
        log.info("Delete instance %s", registration)
        mi.delete(registration)
