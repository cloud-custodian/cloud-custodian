# Copyright 2017 Capital One Services, LLC
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
Utility functions for working with inventories.
"""

import csv
import datetime
import functools
import fnmatch
import gzip
import json
import random
import tempfile

from six.moves.urllib_parse import unquote_plus

from c7n.utils import chunks


def load_manifest_file(client, bucket, schema, versioned, ofilter, key_info):
    """Given an inventory csv file, return an iterator over keys
    """
    # To avoid thundering herd downloads, we do an immediate yield for
    # interspersed i/o
    yield None

    # Inline these values to avoid the local var lookup, they are constants
    # rKey = schema['Key'] # 1
    # rIsLatest = schema['IsLatest'] # 3
    # rVersionId = schema['VersionId'] # 2

    with tempfile.NamedTemporaryFile() as fh:
        client.download_fileobj(Bucket=bucket, Key=key_info['key'], Fileobj=fh)
        fh.seek(0)
        reader = csv.reader(gzip.GzipFile(fileobj=fh, mode='r'))
        for key_set in chunks(reader, 1000):
            keys = []
            for kr in key_set:
                k = kr[1]
                if ofilter(kr):
                    continue
                k = unquote_plus(k)
                if versioned:
                    if kr[3] == 'true':
                        keys.append((k, kr[2], True))
                    else:
                        keys.append((k, kr[2]))
                else:
                    keys.append(k)
            yield keys


class ObjectFilter(object):

    def __init__(self, data, schema):
        self.data = data
        self.schema = schema
        self.max_size = 'max-size' in data and self.data['max-size'] or None
        self.min_size = 'min-size' in data and self.data['min-size'] or None
        self.extensions = 'extensions' in data and set(self.data['extensions'])
        self.encrypted = 'encrypted' in data and set(self.data['encryption'])
        if 'EncryptionStatus' not in schema:
            self.encrypted = None
        self.last_modified = 'last-modified' in data and self.data['last-modified'] or None
        if self.last_modified:
            self.last_modified = datetime.datetime.utcnow() - datetime.timedelta(
                days=self.data['last-modified'])

    def __call__(self, kr):
        if self.max_size or self.min_size:
            size = kr[self.schema['Size']]
            if self.max_size and size > self.max_size:
                return True
            if self.min_size and size < self.min_size:
                return True
        if self.last_modified:
            modified = kr[self.schema['LastModified']]
            if self.last_modified < modified:
                return True
        if self.extensions:
            kext = kr[self.schema['Key']].rsplit('.', 1)[-1]
            if kext not in self.extensions:
                return True
        if self.encrypted:
            if kr[self.schema['EncryptionStatus']] not in self.encrypted:
                return True
        return False


def load_bucket_inventory(
        client, inventory_bucket, inventory_prefix, versioned, ifilters):
    """Given an inventory location for a bucket, return an iterator over keys

    on the most recent delivered manifest.
    """
    now = datetime.datetime.now()
    key_prefix = "%s/%s" % (inventory_prefix, now.strftime('%Y-%m-'))
    keys = client.list_objects(
        Bucket=inventory_bucket, Prefix=key_prefix).get('Contents', [])
    keys = [k['Key'] for k in keys if k['Key'].endswith('.json')]
    keys.sort()
    if not keys:
        # no manifest delivery
        return None
    latest_manifest = keys[-1]
    manifest = client.get_object(Bucket=inventory_bucket, Key=latest_manifest)
    manifest_data = json.load(manifest['Body'])

    # schema as column name to column index mapping
    schema = dict([(k, i) for i, k in enumerate(
        [n.strip() for n in manifest_data['fileSchema'].split(',')])])

    ofilter = ObjectFilter(ifilters, schema)
    processor = functools.partial(
        load_manifest_file, client, inventory_bucket,
        schema, versioned, ofilter)
    generators = map(processor, manifest_data.get('files', ()))
    return random_chain(generators)


def random_chain(generators):
    """Generator to generate a set of keys from
    from a set of generators, each generator is selected
    at random and consumed to exhaustion.
    """
    while generators:
        g = random.choice(generators)
        try:
            v = g.next()
            if v is None:
                continue
            yield v
        except StopIteration:
            generators.remove(g)


def get_bucket_inventory(client, bucket, inventory_id):
    """Check a bucket for a named inventory, and return the destination."""
    inventories = client.list_bucket_inventory_configurations(
        Bucket=bucket).get('InventoryConfigurationList', [])
    inventories = {i['Id']: i for i in inventories}
    found = fnmatch.filter(inventories, inventory_id)
    if not found:
        return None

    i = inventories[found.pop()]
    s3_info = i['Destination']['S3BucketDestination']
    return {'bucket': s3_info['Bucket'].rsplit(':')[-1],
            'prefix': "%s/%s/%s" % (s3_info['Prefix'], bucket, i['Id'])}
