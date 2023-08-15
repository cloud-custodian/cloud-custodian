# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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

import csv
from datetime import datetime
import gzip
import io
import json
import logging
import os
from tabulate import tabulate

from botocore.compat import OrderedDict
from dateutil.parser import parse as date_parse

from c7n.executor import ThreadPoolExecutor
from c7n.utils import local_session, dumps, jmespath_search, jmespath_compile

log = logging.getLogger('custodian.reports')


def strip_output_path(path, policy_name):
    """Remove the date portion from an object storage output path.
    This effectively removes any trailing path segments that follow
    the last occurrence of the policy name.

    >>> strip_output_path(
    ...   '/logs/my-policy-name/2020/01/01/01'
    ...   'my-policy-name'
    ... )
    logs/my-policy-name
    """
    return ''.join(path.strip('/').rpartition(policy_name)[:-1])


def report(policies, start_date, options, output_fh, raw_output_fh=None):
    """Format a policy's extant records into a report."""
    regions = {p.options.region for p in policies}
    policy_names = {p.name for p in policies}
    formatter = Formatter(
        policies[0].resource_manager.resource_type,
        extra_fields=options.field,
        include_default_fields=not options.no_default_fields,
        include_region=len(regions) > 1,
        include_policy=len(policy_names) > 1
    )

    records = []
    for policy in policies:
        # initialize policy execution context for output access
        policy.ctx.initialize()
        if policy.ctx.output.type == 's3':
            policy_records = record_set(
                policy.session_factory,
                policy.ctx.output.config['netloc'],
                strip_output_path(policy.ctx.output.config['path'], policy.name),
                start_date)
        else:
            policy_records = fs_record_set(policy.ctx.log_dir, policy.name)

        log.debug("Found %d records for region %s", len(policy_records), policy.options.region)

        for record in policy_records:
            record['policy'] = policy.name
            record['region'] = policy.options.region

        records += policy_records

    rows = formatter.to_csv(records, unique=not options.all_findings)

    if options.format == 'csv':
        writer = csv.writer(output_fh, formatter.headers(), quoting=csv.QUOTE_ALL)
        writer.writerow(formatter.headers())
        writer.writerows(rows)
    elif options.format == 'json':
        print(dumps(records, indent=2))
    else:
        # We special case CSV, and for other formats we pass to tabulate
        print(tabulate(rows, formatter.headers(), tablefmt=options.format))

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
            value = jmespath_search(list_field, record)
            if value is None:
                value = ''
            else:
                value = ', '.join([str(v) for v in value])
        elif field.startswith(count_prefix):
            count_field = field.replace(count_prefix, '', 1)
            value = jmespath_search(count_field, record)
            if value is None:
                value = ''
            else:
                value = str(len(value))
        else:
            value = jmespath_search(field, record)
            if value is None:
                value = ''
            if not isinstance(value, str):
                value = str(value)
        vals.append(value)
    return vals


class Formatter:

    def __init__(self, resource_type, extra_fields=(), include_default_fields=True,
                 include_region=False, include_policy=False, fields=()):

        # Lookup default fields for resource type.
        model = resource_type
        self._id_field = model.id
        self._date_field = getattr(model, 'date', None)

        fields = OrderedDict(fields)
        mfields = getattr(model, 'default_report_fields', None)
        if not mfields:
            mfields = [model.id]
            if model.name != model.id:
                mfields.append(model.name)
            if getattr(model, 'date', None):
                mfields.append(model.date)

        if include_default_fields:
            fields.update(OrderedDict(zip(mfields, mfields)))

        for index, field in enumerate(extra_fields):
            # TODO this type coercion should be done at cli input, not here
            h, cexpr = field.split('=', 1)
            fields[h] = cexpr

        # Add these at the end so that they are the last fields
        if include_default_fields:
            if include_region:
                fields['Region'] = 'region'

            if include_policy:
                fields['Policy'] = 'policy'

        self.fields = fields

    def headers(self):
        return self.fields.keys()

    def extract_csv(self, record):
        tag_map = {t['Key']: t['Value'] for t in record.get('Tags', ())}
        return _get_values(record, self.fields.values(), tag_map)

    def uniq_by_id(self, records):
        """Only the first record for each id"""
        uniq = []
        keys = set()
        compiled = None
        if '.' in self._id_field:
            compiled = jmespath_compile(self._id_field)
        for rec in records:
            if compiled:
                rec_id = compiled.search(rec)
            else:
                rec_id = rec[self._id_field]
            if rec_id not in keys:
                uniq.append(rec)
                keys.add(rec_id)
        return uniq

    def to_csv(self, records, reverse=True, unique=True):
        if not records:
            return []

        # Sort before unique to get the first/latest record
        date_sort = ('CustodianDate' in records[0] and 'CustodianDate' or
                     self._date_field)
        if date_sort:
            records.sort(
                key=lambda r: r[date_sort], reverse=reverse)

        if unique:
            uniq = self.uniq_by_id(records)
            log.debug("Uniqued from %d to %d" % (len(records), len(uniq)))
        else:
            uniq = records
            log.debug("Selected %d record(s)" % len(records))
        rows = list(map(self.extract_csv, uniq))
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


def record_set(session_factory, bucket, key_prefix, start_date, specify_hour=False):
    """Retrieve all s3 records for the given policy output url

    From the given start date.
    """

    s3 = local_session(session_factory).client('s3')

    records = []
    key_count = 0

    date = start_date.strftime('%Y/%m/%d')
    if specify_hour:
        date += "/{}".format(start_date.hour)
    else:
        date += "/00"

    marker = "{}/{}/resources.json.gz".format(key_prefix.strip("/"), date)

    p = s3.get_paginator('list_objects_v2').paginate(
        Bucket=bucket,
        Prefix=key_prefix.strip('/') + '/',
        StartAfter=marker,
    )

    with ThreadPoolExecutor(max_workers=20) as w:
        for key_set in p:
            if 'Contents' not in key_set:
                continue
            keys = [k for k in key_set['Contents']
                    if k['Key'].endswith('resources.json.gz')]
            key_count += len(keys)
            futures = map(lambda k: w.submit(
                get_records, bucket, k, session_factory), keys)

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
    blob = io.BytesIO(result['Body'].read())

    records = json.load(gzip.GzipFile(fileobj=blob))
    log.debug("bucket: %s key: %s records: %d",
              bucket, key['Key'], len(records))
    for r in records:
        r['CustodianDate'] = custodian_date
    return records
