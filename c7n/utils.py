# Copyright 2015-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from botocore.exceptions import ClientError

import boto3
import copy
import csv
from datetime import datetime, timedelta
import functools
import json
import itertools
import logging
import os
import random
import re
import threading
import time
import six
import sys


from c7n import ipaddress

# Try to place nice in lambda exec environment
# where we don't require yaml
try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None
else:
    try:
        from yaml import CSafeLoader
        SafeLoader = CSafeLoader
    except ImportError:  # pragma: no cover
        try:
            from yaml import SafeLoader
        except ImportError:
            SafeLoader = None

log = logging.getLogger('custodian.utils')


class UnicodeWriter:
    """utf8 encoding csv writer."""

    def __init__(self, f, dialect=csv.excel, **kwds):
        self.writer = csv.writer(f, dialect=dialect, **kwds)
        if sys.version_info.major == 3:
            self.writerows = self.writer.writerows
            self.writerow = self.writer.writerow

    def writerow(self, row):
        self.writer.writerow([s.encode("utf-8") for s in row])

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


class VarsSubstitutionError(Exception):
    pass


def load_file(path, format=None, vars=None):
    if format is None:
        format = 'yaml'
        _, ext = os.path.splitext(path)
        if ext[1:] == 'json':
            format = 'json'

    with open(path) as fh:
        contents = fh.read()

        if vars:
            try:
                contents = contents.format(**vars)
            except IndexError as e:
                msg = 'Failed to substitute variable by positional argument.'
                raise VarsSubstitutionError(msg)
            except KeyError as e:
                msg = 'Failed to substitute variables.  KeyError on {}'.format(str(e))
                raise VarsSubstitutionError(msg)

        if format == 'yaml':
            try:
                return yaml_load(contents)
            except yaml.YAMLError as e:
                log.error('Error while loading yaml file %s', path)
                log.error('Skipping this file.  Error message below:\n%s', e)
                return None
        elif format == 'json':
            return loads(contents)


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
    return json.dumps(evt, indent=2)


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
     - props: additional key value properties
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


def group_by(resources, key):
    """Return a mapping of key value to resources with the corresponding value.

    Key may be specified as dotted form for nested dictionary lookup
    """
    resource_map = {}
    parts = key.split('.')
    for r in resources:
        v = r
        for k in parts:
            v = v.get(k)
            if not isinstance(v, dict):
                break
        resource_map.setdefault(v, []).append(r)
    return resource_map


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
            list(map(camelResource, v))
    return obj


def get_account_id_from_sts(session):
    response = session.client('sts').get_caller_identity()
    return response.get('Account')


def get_account_alias_from_sts(session):
    response = session.client('iam').list_account_aliases()
    aliases = response.get('AccountAliases', ())
    return aliases and aliases[0] or ''


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


def reset_session_cache():
    setattr(CONN_CACHE, 'session', None)
    setattr(CONN_CACHE, 'time', 0)


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
    return '%s-%s-%s' % (prefix, db_identifier, now.strftime('%Y-%m-%d-%H-%M'))


def get_retry(codes=(), max_attempts=8, min_delay=1, log_retries=False):
    """Decorator for retry boto3 api call on transient errors.

    https://www.awsarchitectureblog.com/2015/03/backoff.html
    https://en.wikipedia.org/wiki/Exponential_backoff

    :param codes: A sequence of retryable error codes.
    :param max_attempts: The max number of retries, by default the delay
           time is proportional to the max number of attempts.
    :param log_retries: Whether we should log retries, if specified
           specifies the level at which the retry should be logged.
    :param _max_delay: The maximum delay for any retry interval *note*
           this parameter is only exposed for unit testing, as its
           derived from the number of attempts.

    Returns a function for invoking aws client calls that
    retries on retryable error codes.
    """
    max_delay = max(min_delay, 2) ** max_attempts

    def _retry(func, *args, **kw):
        for idx, delay in enumerate(
                backoff_delays(min_delay, max_delay, jitter=True)):
            try:
                return func(*args, **kw)
            except ClientError as e:
                if e.response['Error']['Code'] not in codes:
                    raise
                elif idx == max_attempts - 1:
                    raise
                if log_retries:
                    worker_log.log(
                        log_retries,
                        "retrying %s on error:%s attempt:%d last delay:%0.2f",
                        func, e.response['Error']['Code'], idx, delay)
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
        v = klass(six.text_type(value))
    except (ipaddress.AddressValueError, ValueError):
        v = None
    return v


class IPv4Network(ipaddress.IPv4Network):

    # Override for net 2 net containment comparison
    def __contains__(self, other):
        if other is None:
            return False
        if isinstance(other, ipaddress._BaseNetwork):
            return self.supernet_of(other)
        return super(IPv4Network, self).__contains__(other)


worker_log = logging.getLogger('c7n.worker')


def worker(f):
    """Generic wrapper to log uncaught exceptions in a function.

    When we cross concurrent.futures executor boundaries we lose our
    traceback information, and when doing bulk operations we may tolerate
    transient failures on a partial subset. However we still want to have
    full accounting of the error in the logs, in a format that our error
    collection (cwl subscription) can still pickup.
    """
    def _f(*args, **kw):
        try:
            return f(*args, **kw)
        except Exception:
            worker_log.exception(
                'Error invoking %s',
                "%s.%s" % (f.__module__, f.__name__))
            raise
    functools.update_wrapper(_f, f)
    return _f


def reformat_schema(model):
    """ Reformat schema to be in a more displayable format. """
    if not hasattr(model, 'schema'):
        return "Model '{}' does not have a schema".format(model)

    if 'properties' not in model.schema:
        return "Schema in unexpected format."

    ret = copy.deepcopy(model.schema['properties'])

    if 'type' in ret:
        del(ret['type'])

    for key in model.schema.get('required', []):
        if key in ret:
            ret[key]['required'] = True

    return ret


_profile_session = None


def get_profile_session(options):
    global _profile_session
    if _profile_session:
        return _profile_session

    profile = getattr(options, 'profile', None)
    _profile_session = boto3.Session(profile_name=profile)
    return _profile_session


def format_string_values(obj, *args, **kwargs):
    """
    Format all string values in an object.
    Return the updated object
    """
    if isinstance(obj, dict):
        new = {}
        for key in obj.keys():
            new[key] = format_string_values(obj[key], *args, **kwargs)
        return new
    elif isinstance(obj, list):
        new = []
        for item in obj:
            new.append(format_string_values(item, *args, **kwargs))
        return new
    elif isinstance(obj, six.string_types):
        return obj.format(*args, **kwargs)
    else:
        return obj


class FormatDate(object):
    """a datetime wrapper with extended pyformat syntax"""

    date_increment = re.compile('\+[0-9]+[Mdh]')

    def __init__(self, d=None):
        self._d = d

    @classmethod
    def utcnow(cls):
        return cls(datetime.utcnow())

    def __getattr__(self, k):
        return getattr(self._d, k)

    def __format__(self, fmt=None):
        d = self._d
        increments = self.date_increment.findall(fmt)
        for i in increments:
            p = {}
            if i[-1] == 'M':
                p['minutes'] = float(i[1:-1])
            if i[-1] == 'h':
                p['hours'] = float(i[1:-1])
            if i[-1] == 'd':
                p['days'] = float(i[1:-1])
            d = d + timedelta(**p)
        if increments:
            fmt = self.date_increment.sub("", fmt)
        return d.__format__(fmt)
