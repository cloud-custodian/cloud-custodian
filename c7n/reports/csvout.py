# Copyright 2016 Capital One Services, LLC
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
Reporting Tools
---------------

Provides reporting tools against cloud-custodian's json output records.

For each policy execution custodian stores structured output
in json format of the records a policy has filtered to
in an s3 bucket.

These represent the records matching the policy filters
that the policy will apply actions to.

The reporting mechanism here simply fetches those records
over a given time interval and constructs a resource type
specific report on them.


CLI Usage
=========

.. code-block:: bash

   $ custodian report -s s3://cloud-custodian-xyz/policies \\
     -p ec2-tag-compliance-terminate -v > terminated.csv


TODO

The type specific formatting needs easy customization, 
a config file for the report or custodian, or named formats
with format spec on the cli are all viable.
"""

from concurrent.futures import as_completed

from cStringIO import StringIO
import csv
from datetime import datetime
import gzip
import json
import logging
import os

from dateutil.parser import parse as date_parse

from c7n.executor import ThreadPoolExecutor
from c7n.utils import local_session, dumps


log = logging.getLogger('custodian.reports')


def report(policy, start_date, output_fh, raw_output_fh=None, filters=None):
    """Format a policy's extant records into a report."""
    formatter = RECORD_TYPE_FORMATTERS.get(policy.resource_type)

    if formatter is None:
        raise ValueError(
            "No formatter for resource type %s, valid: %s" % (
                policy.resource_type, ", ".join(RECORD_TYPE_FORMATTERS)))

    if policy.ctx.output_path.startswith('s3'):
        records = record_set(
            policy.session_factory,
            policy.ctx.output.bucket,
            policy.ctx.output.key_prefix,
            start_date)
    else:
        records = fs_record_set(policy.ctx.output_path, policy.name)

    rows = formatter.to_csv(records)

    writer = csv.writer(output_fh, formatter.headers())
    writer.writerow(formatter.headers())
    writer.writerows(rows)

    if raw_output_fh is not None:
        dumps(records, raw_output_fh, indent=2)


class Formatter(object):
    def __init__(self, id_field, headers):
        self._id_field = id_field
        self._headers = headers

    def csv_fields(self, record, tag_map):
        '''Must be implemented by subclass'''
        raise Exception("Method not implemented by subclass: csv_fields")

    def filter_record(self, record):
        '''Override in subclass if filtering needed.'''
        return True

    def headers(self):
        return self._headers

    def extract_csv(self, record):
        tag_map = {t['Key']: t['Value'] for t in record.get('Tags', ())}
        return self.csv_fields(record, tag_map)

    def uniq_by_id(self, records):
        """Only the first record for each id"""
        uniq = []
        keys = set()
        for rec in records:
            rec_id = rec[self._id_field]
            if rec_id not in keys:
                uniq.append(rec)
                keys.add(rec_id)
        return uniq

    def to_csv(self, records, reverse=True):
        if not records:
            return []

        filtered = filter(self.filter_record, records)
        log.debug("Filtered from %d to %d" % (len(records), len(filtered)))
        if 'CustodianDate' in records[0]:
            filtered.sort(
                key=lambda r: r['CustodianDate'], reverse=reverse)
        uniq = self.uniq_by_id(filtered)
        log.debug("Uniqued from %d to %d" % (len(filtered), len(uniq)))
        rows = map(self.extract_csv, uniq)
        return rows


class S3Formatter(Formatter):

    def __init__(self):
        super(S3Formatter, self).__init__(
            'Name',
            ['name',
             'creation-date',
             'global-permissions',
             'ownercontact',
             'asv',
             'env'])

    def csv_fields(self, record, tag_map):
        return [
            record['Name'],
            record['CreationDate'],
            # s3 formatter is used for multiple s3 rules.
            # the buckets may not have any global permissions
            ','.join(record.get('GlobalPermissions', '')),
            tag_map.get("OwnerContact", ""),
            tag_map.get("ASV", ""),
            tag_map.get("CMDBEnvironment", ""),
        ]


class EC2Formatter(Formatter):
    def __init__(self):
        super(EC2Formatter, self).__init__(
            'InstanceId',
            ['action-date', 'instance-id', 'name', 'instance-type', 'launch',
             'vpc-id', 'ip-addr', 'asv', 'env', 'owner'])

    def filter_record(self, record):
        return record['State']['Name'] != 'terminated'

    def csv_fields(self, record, tag_map):
        return [
            record['CustodianDate'].strftime("%Y-%m-%d"),
            record['InstanceId'],
            tag_map.get('Name', ''),
            record['InstanceType'],
            record['LaunchTime'],
            record.get('VpcId', ''),
            record.get('PrivateIpAddress', ''),
            tag_map.get("ASV", ""),
            tag_map.get("CMDBEnvironment", ""),
            tag_map.get("OwnerContact", ""),
        ]


class ELBFormatter(Formatter):
    def __init__(self):
        super(ELBFormatter, self).__init__(
            'DNSName',
            ['name', 'dns name', 'vpc-id', 'asv', 'env', 'owner'])

    def csv_fields(self, record, tag_map):
        return [
            record['LoadBalancerName'],
            record['DNSName'],
            record['VPCId'],
            tag_map.get("ASV", ""),
            tag_map.get("CMDBEnvironment", ""),
            tag_map.get("OwnerContact", "")
        ]


class RDSFormatter(Formatter):
    def __init__(self):
        super(RDSFormatter, self).__init__(
            'DBInstanceIdentifier',
            ['instance id', 'db name', 'creation time', 'encrypted', 'publicly accessible', 'asv', 'env', 'owner'])

    def csv_fields(self, record, tag_map):
        return [
            record['DBInstanceIdentifier'],
            record.get('DBName', ''),
            record['StorageEncrypted'],
            record['PubliclyAccessible'],
            tag_map.get("ASV", ""),
            tag_map.get("CMDBEnvironment", ""),
            tag_map.get("OwnerContact", "")
        ]


class ASGFormatter(Formatter):
    def __init__(self):
        super(ASGFormatter, self).__init__(
            'AutoScalingGroupName',
            ['name', 'instance-count', 'asv', 'env', 'owner'])

    def csv_fields(self, record, tag_map):
        return [
            record['AutoScalingGroupName'],
            str(len(record['Instances'])),
            tag_map.get("ASV", ""),
            tag_map.get("CMDBEnvironment", ""),
            tag_map.get("OwnerContact", "")
        ]


class AMIFormatter(Formatter):
    def __init__(self):
        super(AMIFormatter, self).__init__(
            'ImageId',
            ['id', 'name'])

    def csv_fields(self, record, tag_map):
        return [
            record['ImageId'],
            record['Name']
        ]


class EBSFormatter(Formatter):
    def __init__(self):
        super(EBSFormatter, self).__init__(
            'VolumeId',
            ['id', 'instance-id', 'asv', 'env', 'owner'])

    def csv_fields(self, record, tag_map):
        instance_id = (record['Attachments'][0]['InstanceId'] if
                       len(record['Attachments']) > 0 else 'Unattached')
        return [
            record['VolumeId'],
            instance_id,
            tag_map.get("ASV", ""),
            tag_map.get("CMDBEnvironment", ""),
            tag_map.get("OwnerContact", "")
        ]

# FIXME: Should we use a PluginRegistry instead?
RECORD_TYPE_FORMATTERS = {
    'ami': AMIFormatter(),
    'asg': ASGFormatter(),
    'ebs': EBSFormatter(),
    'ec2': EC2Formatter(),
    'elb': ELBFormatter(),
    'rds': RDSFormatter(),
    's3': S3Formatter()
}


def fs_record_set(output_path, policy_name):
    record_path = os.path.join(output_path, 'resources.json')
    
    if not os.path.exists(record_path):
        return []
    
    mdate = datetime.fromtimestamp(
        os.stat(record_path).st_ctime)
    
    with open(record_path) as fh:
        records = json.load(fh)
        [r.__setitem__('CustodianDate', mdate) for r in records]
        return records

    
def record_set(session_factory, bucket, key_prefix, start_date):
    """Retrieve all s3 records for the given policy output url

    From the given start date.
    """

    s3 = local_session(session_factory).client('s3')

    records = []
    key_count = 0

    marker = key_prefix.strip("/") + "/" + start_date.strftime(
         '%Y/%m/%d/00') + "/resources.json.gz"

    p = s3.get_paginator('list_objects').paginate(
        Bucket=bucket,
        Prefix=key_prefix.strip('/') + '/',
        Marker=marker
    )

    with ThreadPoolExecutor(max_workers=20) as w:
        for key_set in p:
            if 'Contents' not in key_set:
                continue
            keys = [k for k in key_set['Contents']
                    if k['Key'].endswith('resources.json.gz')]
            key_count += len(keys)
            futures = map(lambda k: w.submit(get_records, bucket, k, session_factory), keys)

            for f in as_completed(futures):
                records.extend(f.result())

    log.info("Fetched %d records across %d files" % (
        len(records), key_count))
    return records


def get_records(bucket, key, session_factory):
    # we're doing a lot of this in memory, worst case
    # though we're talking about a 10k objects, else
    # we should spool to temp files

    # key ends with 'YYYY/mm/dd/HH/resources.json.gz'
    # so take the date parts only
    date_str = '-'.join(key['Key'].rsplit('/', 5)[-5:-1])
    custodian_date = date_parse(date_str)
    s3 = local_session(session_factory).client('s3')
    result = s3.get_object(Bucket=bucket, Key=key['Key'])
    blob = StringIO(result['Body'].read())

    records = json.load(gzip.GzipFile(fileobj=blob))
    log.debug("bucket: %s key: %s records: %d",
              bucket, key['Key'], len(records))
    for r in records:
        r['CustodianDate'] = custodian_date
    return records
