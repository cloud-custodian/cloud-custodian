# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
from boto3.dynamodb import conditions
from c7n.utils import format_event

log = logging.getLogger('sphere11.db')


class LockDb:

    STATE_LOCKED = "locked"
    STATE_UNLOCKED = "unlocked"
    STATE_PENDING = "pending"

    def __init__(self, session, table_name, endpoint=None):
        self.client = session.client('dynamodb', endpoint_url=endpoint)
        self.table = session.resource(
            'dynamodb', endpoint_url=endpoint).Table(table_name)
        self.table_name = table_name

    def record(self, account_id, resource_id):
        result = self.table.get_item(
            Key={
                'AccountId': account_id,
                "ResourceId": resource_id},
            ConsistentRead=True)
        result.pop('ResponseMetadata')
        if result:
            return result['Item']
        return None

    def save(self, record):
        try:
            log.info("Serializing record %s", format_event(record))
        except TypeError:
            pass
        self.table.put_item(Item=record)

    def iter_pending(self, account_id):
        expr = conditions.Key('AccountId').eq(account_id)
        expr & conditions.Key("LockStatus").eq("pending")
        results = self.table.query(
            IndexName='PendingLocks', KeyConditionExpression=expr)
        return results.get('Items', ())

    def iter_resources(self, account_id, resource_type=None):
        expr = conditions.Key('AccountId').eq(account_id)
        if resource_type == "security-group":
            expr = expr & conditions.Key('ResourceId').between('sg-', 'vpc-')
        elif resource_type == "vpc":
            expr = expr & conditions.Key('ResourceId').begins_with('vpc-')
        results = self.table.scan(FilterExpression=expr)
        return results['Items']

    def info(self, account_id, resource_id, parent_id):
        """Check if a resource is locked.

        If a resource has an explicit status we use that, else
        we defer to the parent resource lock status.
        """
        resource = self.record(account_id, resource_id)
        if resource is None and not parent_id:
            return {'ResourceId': resource_id,
                    'LockStatus': self.STATE_UNLOCKED}
        elif resource is None:
            parent = self.record(account_id, parent_id)
            if parent is None:
                return {'ResourceId': resource_id,
                        'ParentId': parent_id,
                        'LockStatus': self.STATE_UNLOCKED}
            parent['ResourceId'] = resource_id
            parent['ParentId'] = parent_id
            parent['LockType'] = 'parent'
            return parent
        if resource['ResourceId'].startswith('vpc-'):
            return resource
        if resource['ResourceId'].startswith('sg-'):
            return resource

    def provision(self, read_capacity=5, write_capacity=1):
        names = set()
        for p in self.client.get_paginator('list_tables').paginate():
            names.update(p['TableNames'])

        if self.table_name in names:
            return False

        self.client.create_table(
            TableName=self.table_name,
            KeySchema=[
                {
                    "AttributeName": "AccountId",
                    "KeyType": "HASH"
                },
                {
                    "AttributeName": "ResourceId",
                    "KeyType": "RANGE"
                }
            ],
            AttributeDefinitions=[
                {
                    "AttributeName": "ResourceId",
                    "AttributeType": "S"
                },
                {
                    "AttributeName": "AccountId",
                    "AttributeType": "S"
                },
                {
                    "AttributeName": "LockStatus",
                    "AttributeType": "S"
                }
            ],
            LocalSecondaryIndexes=[{
                'IndexName': 'PendingLocks',
                'Projection': {
                    'ProjectionType': 'INCLUDE',
                    'NonKeyAttributes': ['LockDate'],
                },
                'KeySchema': [
                    {
                        'AttributeName': 'AccountId',
                        'KeyType': 'HASH'
                    },
                    {
                        'AttributeName': 'LockStatus',
                        'KeyType': 'RANGE'
                    }
                ],
            }],
            ProvisionedThroughput={
                "ReadCapacityUnits": read_capacity,
                "WriteCapacityUnits": write_capacity
            },
            StreamSpecification={
                'StreamEnabled': True,
                'StreamViewType': 'NEW_IMAGE'
            }
        )
        return True
