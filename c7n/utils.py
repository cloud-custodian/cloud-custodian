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
from botocore.exceptions import ClientError
from datetime import datetime

import copy
import json
import itertools
import random
import threading
import time
import ipaddress


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


class Bag(dict):

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


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


def camelResource(obj):
    """Some sources from apis return lowerCased where as describe calls

    always return TitleCase, this function turns the former to the later
    """
    if not isinstance(obj, dict):
        return obj
    for k in list(obj.keys()):
        v = obj.pop(k)
        obj["%s%s" % (k[0].upper(), k[1:])] = v
        if isinstance(v, dict):
            camelResource(v)
        elif isinstance(v, list):
            map(camelResource, v)
    return obj


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


def generate_arn(
        service, resource, partition='aws',
        region=None, account_id=None, resource_type=None, separator='/'):
    """Generate an Amazon Resource Name.
    See http://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html.
    """
    arn = 'arn:%s:%s:%s:%s:' % (
        partition, service, region if region else '', account_id if account_id else '')
    if resource_type:
        arn = arn + '%s%s%s' % (resource_type, separator, resource)
    else:
        arn = arn + resource
    return arn


def snapshot_identifier(prefix, db_identifier):
    """Return an identifier for a snapshot of a database or cluster.
    """
    now = datetime.now()
    return '%s-%s-%s' % (prefix, db_identifier, now.strftime('%Y-%m-%d'))


def get_retry(codes=(), max_attempts=8):
    """Retry a boto3 api call on transient errors.

    https://www.awsarchitectureblog.com/2015/03/backoff.html
    https://en.wikipedia.org/wiki/Exponential_backoff

    :param codes: A sequence of retryable error codes

    returns a function for invoking aws client calls that
    retries on retryable error codes.
    """
    max_delay = 2 ** max_attempts

    def _retry(func, *args, **kw):
        for idx, delay in enumerate(backoff_delays(1, max_delay, jitter=True)):
            try:
                return func(*args, **kw)
            except ClientError as e:
                if e.response['Error']['Code'] not in codes:
                    raise
                elif idx == max_attempts - 1:
                    raise
            time.sleep(delay)
    return _retry


def backoff_delays(start, stop, factor=2.0, jitter=False):
    """Geometric backoff sequence w/ jitter
    """
    cur = start
    while cur <= stop:
        if jitter:
            yield cur - (cur * random.random())
        else:
            yield cur
        cur = cur * factor


def parse_cidr(value):
    """Process cidr ranges."""
    klass = IPv4Network
    if '/' not in value:
        klass = ipaddress.ip_address
    try:
        v = klass(unicode(value))
    except (ipaddress.AddressValueError, ValueError):
        v = None
    return v


class IPv4Network(ipaddress.IPv4Network):

    # Override for net 2 net containment comparison
    def __contains__(self, other):
        if isinstance(other, ipaddress._BaseNetwork):
            return self.supernet_of(other)
        return super(IPv4Network, self).__contains__(other)
