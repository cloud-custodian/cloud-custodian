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
'''
Supporting utilities for various implementations
of PolicyExecutionMode.get_logs()
'''
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import re
import time
from botocore.exceptions import ClientError
from concurrent.futures import as_completed
from cStringIO import StringIO
from datetime import datetime
from dateutil import parser
from dateutil import tz
from gzip import GzipFile

from c7n.executor import ThreadPoolExecutor
from c7n.utils import local_session


log = logging.getLogger('custodian.logs')


def _timestamp_from_string(date_text):
    try:
        date_dt = parser.parse(date_text)
        date_ts = time.mktime(date_dt.timetuple())
        return long(date_ts * 1000)
    except (AttributeError, TypeError, ValueError):
        return 0


def normalized_log_entries(raw_entries):
    '''Mimic the format returned by LambdaManager.logs()'''
    entry_start = '([0-9:, \-]+) - .* - (\w+) - (.*)$'
    entry = None
    # process start/end here - avoid parsing log entries twice
    for line in raw_entries:
        m = re.match(entry_start, line)
        if m:
            # this is the start of a new entry
            # spit out the one previously built up (if any)
            if entry is not None:
                yield entry
            (log_time, log_level, log_text) = m.groups()
            # convert time
            log_timestamp = _timestamp_from_string(log_time)
            # join level and first line of message
            msg = '[{}] {}'.format(log_level, log_text)
            entry = {
                'timestamp': log_timestamp,
                'message': msg,
            }
        else:
            # additional line(s) for entry (i.e. stack trace)
            entry['message'] = entry['message'] + line
    if entry is not None:
        # return the final entry
        yield entry


def log_entries_in_range(entries, start, end):
    '''filter out entries before start and after end'''
    start = _timestamp_from_string(start)
    end = _timestamp_from_string(end)
    for entry in entries:
        log_timestamp = entry.get('timestamp', 0)
        if log_timestamp >= start and log_timestamp <= end:
            yield entry


def log_entries_from_s3(session_factory, output, start, end):
    client = local_session(session_factory).client('s3')
    key_prefix = output.key_prefix.strip('/')
    local_tz = tz.tzlocal()
    start = datetime.fromtimestamp(
        _timestamp_from_string(start) / 1000
    )
    end = datetime.fromtimestamp(
        _timestamp_from_string(end) / 1000
    ).replace(tzinfo=local_tz)
    records = []
    key_count = 0
    log_filename = 'custodian-run.log.gz'
    marker = '{}/{}/{}'.format(
        key_prefix,
        start.strftime('%Y/%m/%d/00'),
        log_filename,
    )
    p = client.get_paginator('list_objects_v2').paginate(
        Bucket=output.bucket,
        Prefix=key_prefix + '/',
        StartAfter=marker,
    )
    with ThreadPoolExecutor(max_workers=20) as w:
        for key_set in p:
            if 'Contents' not in key_set:
                continue
            log_keys = [k for k in key_set['Contents']
                    if k['Key'].endswith(log_filename)]
            keys = [k for k in log_keys if k['LastModified'] < end]
            if len(log_keys) >= 1 and len(keys) == 0:
                # there were logs, but we're now past the end date
                break
            key_count += len(keys)
            futures = map(
                lambda k:
                    w.submit(get_records, output.bucket, k, session_factory),
                keys,
            )

            for f in as_completed(futures):
                records.extend(f.result())

    log.info('Fetched {} records across {} files'.format(
        len(records),
        key_count,
    ))
    return records


def get_records(bucket, key, session_factory):
    client = local_session(session_factory).client('s3')
    result = client.get_object(Bucket=bucket, Key=key['Key'])
    blob = StringIO(result['Body'].read())

    records = GzipFile(fileobj=blob).readlines()
    log.debug("bucket: %s key: %s records: %d",
              bucket, key['Key'], len(records))
    return records


def log_entries_from_group(session, group_name, start, end):
    '''Get logs for a specific log group'''
    logs = session.client('logs')
    log.info("Fetching logs from group: %s" % group_name)
    try:
        logs.describe_log_groups(logGroupNamePrefix=group_name)
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return
        raise
    try:
        log_streams = logs.describe_log_streams(
            logGroupName=group_name,
            orderBy="LastEventTime",
            limit=3,
            descending=True,
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return
        raise
    start = _timestamp_from_string(start)
    end = _timestamp_from_string(end)
    for s in reversed(log_streams['logStreams']):
        result = logs.get_log_events(
            logGroupName=group_name,
            logStreamName=s['logStreamName'],
            startTime=start,
            endTime=end,
        )
        for e in result['events']:
            yield e
