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
from datetime import datetime

import copy
import json
import itertools
import threading
import time



# Try to place nice in lambda exec environment
# where we don't require yaml
try:
    import yaml
except ImportError:
    yaml = None
else:
    try:
        from yaml import CSafeLoader
        SafeLoader = CSafeLoader
    except ImportError:
        try:
            from yaml import SafeLoader
        except ImportError:
            SafeLoader = None


from StringIO import StringIO


def yaml_load(value):
    if yaml is None:
        raise RuntimeError("Yaml not available")
    return yaml.load(value, Loader=SafeLoader)


def loads(body):
    return json.loads(body)


def dumps(data, fh=None, indent=0):
    if fh:
        return json.dump(data, fh, cls=DateTimeEncoder, indent=indent)
    else:
        return json.dumps(data, cls=DateTimeEncoder, indent=indent)


def format_event(evt):
    io = StringIO()
    json.dump(evt, io, indent=2)
    return io.getvalue()


def type_schema(
        type_name, inherits=None, rinherit=None,
        aliases=None, required=None, **props):
    """jsonschema generation helper

    params:
     - type_name: name of the type
     - inherits: list of document fragments that are required via anyOf[$ref]
     - rinherit: use another schema as a base for this, basically work around
                 inherits issues with additionalProperties and type enums.
     - aliases: additional names this type maybe called
     - required: list of required properties, by default 'type' is required
     - **props: additional key value properties
    """
    if aliases:
        type_names = [type_name]
        type_names.extend(aliases)
    else:
        type_names = [type_name]

    if rinherit:
        s = copy.deepcopy(rinherit)
        s['properties']['type'] = {'enum': type_names}
    else:
        s = {
            'type': 'object',
            'properties': {
                'type': {'enum': type_names}}}

    # Ref based inheritance and additional properties don't mix well.
    # http://goo.gl/8UyRvQ
    if not inherits:
        s['additionalProperties'] = False

    s['properties'].update(props)
    if not required:
        required = []
    if isinstance(required, list):
        required.append('type')
    s['required'] = required
    if inherits:
        extended = s
        s = {'allOf': [{'$ref': i} for i in inherits]}
        s['allOf'].append(extended)
    return s


class DateTimeEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)


def chunks(iterable, size=50):
    """Break an iterable into lists of size"""
    batch = []
    for n in iterable:
        batch.append(n)
        if len(batch) % size == 0:
            yield batch
            batch = []
    if batch:
        yield batch


def get_account_id(session):
    iam = session.client('iam')
    return iam.list_roles(MaxItems=1)['Roles'][0]['Arn'].split(":")[4]


def query_instances(session, client=None, **query):
    """Return a list of ec2 instances for the query.
    """
    if client is None:
        client = session.client('ec2')
    p = client.get_paginator('describe_instances')
    results = p.paginate(**query)
    return list(itertools.chain(
        *[r["Instances"] for r in itertools.chain(
            *[pp['Reservations'] for pp in results])]))

CONN_CACHE = threading.local()


def local_session(factory):
    """Cache a session thread local for up to 45m"""
    s = getattr(CONN_CACHE, 'session', None)
    t = getattr(CONN_CACHE, 'time', 0)
    n = time.time()
    if s is not None and t + (60 * 45) > n:
        return s
    s = factory()
    CONN_CACHE.session = s
    CONN_CACHE.time = n
    return s


def annotation(i, k):
    return i.get(k, ())


def set_annotation(i, k, v):
    """
    >>> x = {}
    >>> set_annotation(x, 'marker', 'a')
    >>> annotation(x, 'marker')
    ['a']
    """
    if not isinstance(i, dict):
        raise ValueError("Can only annotate dictionaries")

    if not isinstance(v, list):
        v = [v]

    if k in i:
        ev = i.get(k)
        if isinstance(ev, list):
            ev.extend(v)
    else:
        i[k] = v


def parse_s3(s3_path):
    if not s3_path.startswith('s3://'):
        raise ValueError("invalid s3 path")
    ridx = s3_path.find('/', 5)
    if ridx == -1:
        ridx = None
    bucket = s3_path[5:ridx]
    s3_path = s3_path.rstrip('/')
    if ridx is None:
        key_prefix = ""
    else:
        key_prefix = s3_path[s3_path.find('/', 5):]
    return s3_path, bucket, key_prefix
