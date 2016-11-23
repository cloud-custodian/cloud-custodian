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
import logging
import re
from concurrent.futures import as_completed
from cStringIO import StringIO
from datetime import datetime
from gzip import GzipFile

from c7n.executor import ThreadPoolExecutor
from c7n.utils import timestamp_from_string


log = logging.getLogger('custodian.logs')


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
            log_timestamp = timestamp_from_string(log_time) * 1000
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
    start = timestamp_from_string(start) * 1000
    end = timestamp_from_string(end) * 1000
    for entry in entries:
        log_timestamp = entry.get('timestamp', 0)
        if log_timestamp >= start and log_timestamp <= end:
            yield entry


def log_entries_from_s3(session, output, start):
    client = session.client('s3')
    key_prefix = output.key_prefix.strip('/')
    start = datetime.fromtimestamp(
        timestamp_from_string(start)
    )
    records = []
    key_count = 0
    log_filename = 'custodian-run.log.gz'
    marker = '{}/{}/{}'.format(
        key_prefix,
        start.strftime('%Y/%m/%d/00'),
        log_filename,
    )
    p = client.get_paginator('list_objects').paginate(
        Bucket=output.bucket,
        Prefix=key_prefix + '/',
        Marker=marker,
    )
    with ThreadPoolExecutor(max_workers=20) as w:
        for key_set in p:
            if 'Contents' not in key_set:
                continue
            keys = [k for k in key_set['Contents']
                    if k['Key'].endswith(log_filename)]
            key_count += len(keys)
            futures = map(
                lambda k: w.submit(get_records, output.bucket, k, client), keys
            )

            for f in as_completed(futures):
                records.extend(f.result())

    log.info('Fetched {} records across {} files'.format(
        len(records),
        key_count,
    ))
    return records


def get_records(bucket, key, client):
    result = client.get_object(Bucket=bucket, Key=key['Key'])
    blob = StringIO(result['Body'].read())

    records = GzipFile(fileobj=blob).readlines()
    log.debug("bucket: %s key: %s records: %d",
              bucket, key['Key'], len(records))
    return records
