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


"""

from concurrent.futures import as_completed

from cStringIO import StringIO
import csv
from datetime import datetime
import gzip
import json
import jmespath
import logging
import os
import copy

from dateutil.parser import parse as date_parse

from c7n.executor import ThreadPoolExecutor
from c7n.utils import local_session, dumps


log = logging.getLogger('custodian.reports')


def report(policy, start_date, options, output_fh, raw_output_fh=None, filters=None):
    """Format a policy's extant records into a report."""
    if not policy.resource_manager.report_fields:
        raise ValueError(
            "No formatter configured for resource type '%s', valid options: %s" % (
                policy.resource_type))

    formatter = Formatter(
        policy.resource_manager,
        extra_fields=options.field,
        no_default_fields=options.no_default_fields,
    )

    if policy.ctx.output.use_s3():
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


def _get_values(record, field_list, tag_map):
    tag_prefix = 'tag:'
    list_prefix = 'list:'
    count_prefix = 'count:'
    vals = []
    for field in field_list:
        if field.startswith(tag_prefix):
            tag_field = field.replace(tag_prefix, '', 1)
            value = tag_map.get(tag_field, '')
        elif field.startswith(list_prefix):
            list_field = field.replace(list_prefix, '', 1)
            value = jmespath.search(list_field, record)
            if value is None:
                value = ''
            else:
                value = ', '.join(value)
        elif field.startswith(count_prefix):
            count_field = field.replace(count_prefix, '', 1)
            value = jmespath.search(count_field, record)
            if value is None:
                value = ''
            else:
                value = str(len(value))
        else:
            value = jmespath.search(field, record)
            if value is None:
                value = ''
        vals.append(value)
    return vals


class Formatter(object):
    
    def __init__(self, resource_manager, **kwargs):
        self.resource_manager = resource_manager
        self._id_field = resource_manager.id_field
        self.fields = resource_manager.report_fields
        # Make a copy because we modify the values when we strip off the header
        self.extra_fields = copy.copy(kwargs.get('extra_fields', []))
        self.no_default_fields = kwargs.get('no_default_fields', False)
        self.set_headers()

    def csv_fields(self, record, tag_map):
        return _get_values(record, self.fields, tag_map)

    def set_headers(self):
        self._headers = []
        if not self.no_default_fields:
            self._headers = copy.copy(self.fields)

        for index, field in enumerate(self.extra_fields):
            header, field_minus_header = field.split('=', 1)
            self._headers.append(header)
            self.extra_fields[index] = field_minus_header

    def headers(self):
        return self._headers

    def extract_csv(self, record):
        tag_map = {t['Key']: t['Value'] for t in record.get('Tags', ())}

        output = []
        if not self.no_default_fields:
            output = self.csv_fields(record, tag_map)
            
        output = output + _get_values(record, self.extra_fields, tag_map)
        
        return output

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

        filtered = filter(self.resource_manager.filter_record, records)
        log.debug("Filtered from %d to %d" % (len(records), len(filtered)))
        if 'CustodianDate' in records[0]:
            filtered.sort(
                key=lambda r: r['CustodianDate'], reverse=reverse)
        uniq = self.uniq_by_id(filtered)
        log.debug("Uniqued from %d to %d" % (len(filtered), len(uniq)))
        rows = map(self.extract_csv, uniq)
        return rows


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
