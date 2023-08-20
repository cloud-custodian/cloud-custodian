# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .core import Filter
from datetime import datetime, timedelta
from c7n.utils import type_schema, local_session, chunks
from c7n.query import RetryPageIterator


class ConsecutiveAwsBackupsFilter(Filter):
    """Returns resources where number of consective backups (based on the
    periodicity defined in the filter) is equal to/or greater than n units.
    This filter supports the resources that use AWS Backup service for backups.

    :example:

    .. code-block:: yaml

            policies:
              - name: dynamodb-consecutive-aws-backup-count
                resource: dynamodb-table
                filters:
                  - type: consecutive-aws-backups
                    count: 7
                    period: days
                    status: 'COMPLETED'
    """
    schema = type_schema('consecutive-aws-backups', count={'type': 'number', 'minimum': 1},
        period={'enum': ['hours', 'days', 'weeks']},
        status={'enum': ['COMPLETED', 'PARTIAL', 'DELETING', 'EXPIRED']},
        required=['count', 'period', 'status'])
    permissions = ('backup:ListRecoveryPointsByResource', )
    annotation = 'c7n:AwsBackups'

    def process_resource_set(self, resources):
        arns = self.manager.get_arns(resources)

        client = local_session(self.manager.session_factory).client('backup')
        paginator = client.get_paginator('list_recovery_points_by_resource')
        paginator.PAGE_ITERATOR_CLS = RetryPageIterator
        for r, arn in zip(resources, arns):
            r[self.annotation] = paginator.paginate(
                ResourceArn=arn).build_full_result().get('RecoveryPoints', [])

    def get_date(self, time):
        period = self.data.get('period')
        if period == 'weeks':
            date = (datetime.utcnow() - timedelta(weeks=time)).strftime('%Y-%m-%d')
        elif period == 'hours':
            date = (datetime.utcnow() - timedelta(hours=time)).strftime('%Y-%m-%d-%H')
        else:
            date = (datetime.utcnow() - timedelta(days=time)).strftime('%Y-%m-%d')
        return date

    def process(self, resources, event=None):
        results = []
        retention = self.data.get('count')
        expected_dates = set()
        for time in range(1, retention + 1):
            expected_dates.add(self.get_date(time))

        for resource_set in chunks(
                [r for r in resources if self.annotation not in r], 50):
            self.process_resource_set(resource_set)

        for r in resources:
            backup_dates = set()
            for backup in r[self.annotation]:
                if backup['Status'] == self.data.get('status'):
                    if self.data.get('period') == 'hours':
                        backup_dates.add(backup['CreationDate'].strftime('%Y-%m-%d-%H'))
                    else:
                        backup_dates.add(backup['CreationDate'].strftime('%Y-%m-%d'))

            if expected_dates.issubset(backup_dates):
                results.append(r)
        return results
