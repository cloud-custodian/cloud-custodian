# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy
from collections import UserString
from datetime import datetime, timedelta
from dateutil.tz import tzutc
import json
import itertools
import ipaddress
import logging
import os
import random
import re
import sys
import threading
import time
from urllib import parse as urlparse
from urllib.request import getproxies, proxy_bypass

from dateutil.parser import ParserError, parse

import jmespath
from jmespath import functions
from jmespath.parser import Parser, ParsedResult

from c7n import config
from c7n.exceptions import ClientError, PolicyValidationError

# Try to play nice in a serverless environment, where we don't require yaml

try:
    import yaml
except ImportError:  # pragma: no cover
    SafeLoader = BaseSafeDumper = yaml = None
else:
    try:
        from yaml import CSafeLoader as SafeLoader, CSafeDumper as BaseSafeDumper
    except ImportError:  # pragma: no cover
        from yaml import SafeLoader, SafeDumper as BaseSafeDumper


class SafeDumper(BaseSafeDumper or object):
    def ignore_aliases(self, data):
        return True


log = logging.getLogger('custodian.utils')


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
            except IndexError:
                msg = 'Failed to substitute variable by positional argument.'
                raise VarsSubstitutionError(msg)
            except KeyError as e:
                msg = 'Failed to substitute variables.  KeyError on {}'.format(str(e))
                raise VarsSubstitutionError(msg)

        if format == 'yaml':
            return yaml_load(contents)
        elif format == 'json':
            return loads(contents)


def yaml_load(value):
    if yaml is None:
        raise RuntimeError("Yaml not available")
    return yaml.load(value, Loader=SafeLoader)


def yaml_dump(value):
    if yaml is None:
        raise RuntimeError("Yaml not available")
    return yaml.dump(value, default_flow_style=False, Dumper=SafeDumper)


def loads(body):
    return json.loads(body)


def dumps(data, fh=None, indent=0):
    if fh:
        return json.dump(data, fh, cls=DateTimeEncoder, indent=indent)
    else:
        return json.dumps(data, cls=DateTimeEncoder, indent=indent)


def format_event(evt):
    return json.dumps(evt, indent=2)


def filter_empty(d):
    for k, v in list(d.items()):
        if not v:
            del d[k]
    return d


# We need a minimum floor when examining possible timestamp
# values to distinguish from other numeric time usages. Use
# the S3 Launch Date.
DATE_FLOOR = time.mktime((2006, 3, 19, 0, 0, 0, 0, 0, 0))


def parse_date(v, tz=None):
    """Handle various permutations of a datetime serialization
    to a datetime with the given timezone.

    Handles strings, seconds since epoch, and milliseconds since epoch.
    """

    if v is None:
        return v

    tz = tz or tzutc()

    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.astimezone(tz)
        return v

    if isinstance(v, str) and not v.isdigit():
        try:
            return parse(v).astimezone(tz)
        except (AttributeError, TypeError, ValueError, OverflowError):
            pass

    # OSError on windows -- https://bugs.python.org/issue36439
    exceptions = (ValueError, OSError) if os.name == "nt" else (ValueError)

    if isinstance(v, (int, float, str)):
        try:
            if float(v) > DATE_FLOOR:
                v = datetime.fromtimestamp(float(v)).astimezone(tz)
        except exceptions:
            pass

    if isinstance(v, (int, float, str)):
        # try interpreting as milliseconds epoch
        try:
            if float(v) > DATE_FLOOR:
                v = datetime.fromtimestamp(float(v) / 1000).astimezone(tz)
        except exceptions:
            pass

    return isinstance(v, datetime) and v or None


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
    # https://stackoverflow.com/questions/22689900/json-schema-allof-with-additionalproperties
    if not inherits:
        s['additionalProperties'] = False

    s['properties'].update(props)

    for k, v in props.items():
        if v is None:
            del s['properties'][k]
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
        if isinstance(obj, FormatDate):
            return obj.datetime.isoformat()
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


def camelResource(obj, implicitDate=False, implicitTitle=True):
    """Some sources from apis return lowerCased where as describe calls

    always return TitleCase, this function turns the former to the later

    implicitDate ~ automatically sniff keys that look like isoformat date strings
     and convert to python datetime objects.
    """
    if not isinstance(obj, dict):
        return obj
    for k in list(obj.keys()):
        v = obj.pop(k)
        if implicitTitle:
            ok = "%s%s" % (k[0].upper(), k[1:])
        else:
            ok = k
        obj[ok] = v

        if implicitDate:
            # config service handles datetime differently then describe sdks
            # the sdks use knowledge of the shape to support language native
            # date times, while config just turns everything into a serialized
            # json with mangled keys without type info. to normalize to describe
            # we implicitly sniff keys which look like datetimes, and have an
            # isoformat marker ('T').
            kn = k.lower()
            if isinstance(v, (str, int)) and ('time' in kn or 'date' in kn):
                try:
                    dv = parse_date(v)
                except ParserError:
                    dv = None
                if dv:
                    obj[ok] = dv
        if isinstance(v, dict):
            camelResource(v, implicitDate, implicitTitle)
        elif isinstance(v, list):
            for e in v:
                camelResource(e, implicitDate, implicitTitle)
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


def local_session(factory, region=None):
    """Cache a session thread local for up to 45m"""
    factory_region = getattr(factory, 'region', 'global')
    if region:
        factory_region = region
    s = getattr(CONN_CACHE, factory_region, {}).get('session')
    t = getattr(CONN_CACHE, factory_region, {}).get('time')

    n = time.time()
    if s is not None and t + (60 * 45) > n:
        return s
    s = factory()

    setattr(CONN_CACHE, factory_region, {'session': s, 'time': n})
    return s


def reset_session_cache():
    for k in [k for k in dir(CONN_CACHE) if not k.startswith('_')]:
        setattr(CONN_CACHE, k, {})


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


REGION_PARTITION_MAP = {
    'us-gov-east-1': 'aws-us-gov',
    'us-gov-west-1': 'aws-us-gov',
    'cn-north-1': 'aws-cn',
    'cn-northwest-1': 'aws-cn',
    'us-isob-east-1': 'aws-iso-b',
    'us-iso-east-1': 'aws-iso'
}


def get_partition(region):
    return REGION_PARTITION_MAP.get(region, 'aws')


def generate_arn(
        service, resource, partition='aws',
        region=None, account_id=None, resource_type=None, separator='/'):
    """Generate an Amazon Resource Name.
    See http://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html.
    """
    if region and region in REGION_PARTITION_MAP:
        partition = REGION_PARTITION_MAP[region]
    if service == 's3':
        region = ''
    arn = 'arn:%s:%s:%s:%s:' % (
        partition, service, region if region else '', account_id if account_id else '')
    if resource_type:
        if resource.startswith(separator):
            separator = ''
        arn = arn + '%s%s%s' % (resource_type, separator, resource)
    else:
        arn = arn + resource
    return arn


def snapshot_identifier(prefix, db_identifier):
    """Return an identifier for a snapshot of a database or cluster.
    """
    now = datetime.now()
    return '%s-%s-%s' % (prefix, db_identifier, now.strftime('%Y-%m-%d-%H-%M'))


retry_log = logging.getLogger('c7n.retry')


def get_retry(retry_codes=(), max_attempts=8, min_delay=1, log_retries=False):
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

    def _retry(func, *args, ignore_err_codes=(), **kw):
        for idx, delay in enumerate(
                backoff_delays(min_delay, max_delay, jitter=True)):
            try:
                return func(*args, **kw)
            except ClientError as e:
                if e.response['Error']['Code'] in ignore_err_codes:
                    return
                elif e.response['Error']['Code'] not in retry_codes:
                    raise
                elif idx == max_attempts - 1:
                    raise
                if log_retries:
                    retry_log.log(
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
            yield cur - (cur * random.random() / 5)
        else:
            yield cur
        cur = cur * factor


def parse_cidr(value):
    """Process cidr ranges."""
    if isinstance(value, list) or isinstance(value, set):
        return IPv4List([parse_cidr(item) for item in value])
    klass = IPv4Network
    if '/' not in value:
        klass = ipaddress.ip_address
    try:
        v = klass(str(value))
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

    if (sys.version_info.major == 3 and sys.version_info.minor <= 6):  # pragma: no cover
        @staticmethod
        def _is_subnet_of(a, b):
            try:
                # Always false if one is v4 and the other is v6.
                if a._version != b._version:
                    raise TypeError(f"{a} and {b} are not of the same version")
                return (b.network_address <= a.network_address and
                        b.broadcast_address >= a.broadcast_address)
            except AttributeError:
                raise TypeError(f"Unable to test subnet containment "
                                f"between {a} and {b}")

        def supernet_of(self, other):
            """Return True if this network is a supernet of other."""
            return self._is_subnet_of(other, self)


class IPv4List:
    def __init__(self, ipv4_list):
        self.ipv4_list = ipv4_list

    def __contains__(self, other):
        if other is None:
            return False
        in_networks = any([other in y_elem for y_elem in self.ipv4_list
          if isinstance(y_elem, IPv4Network)])
        in_addresses = any([other == y_elem for y_elem in self.ipv4_list
          if isinstance(y_elem, ipaddress.IPv4Address)])
        return any([in_networks, in_addresses])


def reformat_schema(model):
    """ Reformat schema to be in a more displayable format. """
    if not hasattr(model, 'schema'):
        return "Model '{}' does not have a schema".format(model)

    if 'properties' not in model.schema:
        return "Schema in unexpected format."

    ret = copy.deepcopy(model.schema['properties'])

    if 'type' in ret:
        del ret['type']

    for key in model.schema.get('required', []):
        if key in ret:
            ret[key]['required'] = True

    return ret


# from botocore.utils avoiding runtime dependency for botocore for other providers.
# license apache 2.0
def set_value_from_jmespath(source, expression, value, is_first=True):
    # This takes a (limited) jmespath-like expression & can set a value based
    # on it.
    # Limitations:
    # * Only handles dotted lookups
    # * No offsets/wildcards/slices/etc.
    bits = expression.split('.', 1)
    current_key, remainder = bits[0], bits[1] if len(bits) > 1 else ''

    if not current_key:
        raise ValueError(expression)

    if remainder:
        if current_key not in source:
            # We've got something in the expression that's not present in the
            # source (new key). If there's any more bits, we'll set the key
            # with an empty dictionary.
            source[current_key] = {}

        return set_value_from_jmespath(
            source[current_key],
            remainder,
            value,
            is_first=False
        )

    # If we're down to a single key, set it.
    source[current_key] = value


def format_string_values(obj, err_fallback=(IndexError, KeyError), formatter=None, *args, **kwargs):
    """
    Format all string values in an object.
    Return the updated object
    """
    if isinstance(obj, dict):
        new = {}
        for key in obj.keys():
            new[key] = format_string_values(obj[key], formatter=formatter, *args, **kwargs)
        return new
    elif isinstance(obj, list):
        new = []
        for item in obj:
            new.append(format_string_values(item, formatter=formatter, *args, **kwargs))
        return new
    elif isinstance(obj, str):
        try:
            if formatter:
                return formatter(obj, *args, **kwargs)
            else:
                return obj.format(*args, **kwargs)
        except err_fallback:
            return obj
    else:
        return obj


def parse_url_config(url):
    if url and '://' not in url:
        url += "://"
    conf = config.Bag()
    parsed = urlparse.urlparse(url)
    for k in ('scheme', 'netloc', 'path'):
        conf[k] = getattr(parsed, k)
    for k, v in urlparse.parse_qs(parsed.query).items():
        conf[k] = v[0]
    conf['url'] = url
    return conf


def join_output_path(output_path, *parts):
    # allow users to specify interpolated output paths
    if '{' in output_path:
        return output_path

    if "://" not in output_path:
        return os.path.join(output_path, *parts)

    # handle urls with query strings
    parsed = urlparse.urlparse(output_path)
    updated_path = "/".join((parsed.path, *parts))
    parts = list(parsed)
    parts[2] = updated_path
    return urlparse.urlunparse(parts)


def get_policy_provider(policy_data):
    if isinstance(policy_data['resource'], list):
        provider_name, _ = policy_data['resource'][0].split('.', 1)
    elif '.' in policy_data['resource']:
        provider_name, resource_type = policy_data['resource'].split('.', 1)
    else:
        provider_name = 'aws'
    return provider_name


def get_proxy_url(url):
    proxies = getproxies()
    parsed = urlparse.urlparse(url)

    proxy_keys = [
        parsed.scheme + '://' + parsed.netloc,
        parsed.scheme,
        'all://' + parsed.netloc,
        'all'
    ]

    # Set port if not defined explicitly in url.
    port = parsed.port
    if port is None and parsed.scheme == 'http':
        port = 80
    elif port is None and parsed.scheme == 'https':
        port = 443

    hostname = parsed.hostname is not None and parsed.hostname or ''

    # Determine if proxy should be used based on no_proxy entries.
    # Note this does not support no_proxy ip or cidr entries.
    if proxy_bypass("%s:%s" % (hostname, port)):
        return None

    for key in proxy_keys:
        if key in proxies:
            return proxies[key]

    return None


class DeferredFormatString(UserString):
    """A string that returns itself when formatted

    Let any format spec pass through. This lets us selectively defer
    expansion of runtime variables without losing format spec details.
    """
    def __format__(self, format_spec):
        return "".join(("{", self.data, f":{format_spec}" if format_spec else "", "}"))


class FormatDate:
    """a datetime wrapper with extended pyformat syntax"""

    date_increment = re.compile(r'\+[0-9]+[Mdh]')

    def __init__(self, d=None):
        self._d = d

    def __str__(self):
        return str(self._d)

    @property
    def datetime(self):
        return self._d

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


class QueryParser:

    QuerySchema = {}
    type_name = ''
    multi_value = True
    value_key = 'Values'

    @classmethod
    def parse(cls, data):
        filters = []
        if not isinstance(data, (tuple, list)):
            raise PolicyValidationError(
                "%s Query invalid format, must be array of dicts %s" % (
                    cls.type_name,
                    data))
        for d in data:
            if not isinstance(d, dict):
                raise PolicyValidationError(
                    "%s Query Filter Invalid %s" % (cls.type_name, data))
            if "Name" not in d or cls.value_key not in d:
                raise PolicyValidationError(
                    "%s Query Filter Invalid: Missing Key or Values in %s" % (
                        cls.type_name, data))

            key = d['Name']
            values = d[cls.value_key]

            if not cls.multi_value and isinstance(values, list):
                raise PolicyValidationError(
                    "%s Query Filter Invalid Key: Value:%s Must be single valued" % (
                        cls.type_name, key))
            elif not cls.multi_value:
                values = [values]

            if key not in cls.QuerySchema and not key.startswith('tag:'):
                raise PolicyValidationError(
                    "%s Query Filter Invalid Key:%s Valid: %s" % (
                        cls.type_name, key, ", ".join(cls.QuerySchema.keys())))

            vtype = cls.QuerySchema.get(key)
            if vtype is None and key.startswith('tag'):
                vtype = str

            if not isinstance(values, list):
                raise PolicyValidationError(
                    "%s Query Filter Invalid Values, must be array %s" % (
                        cls.type_name, data,))

            for v in values:
                if isinstance(vtype, tuple):
                    if v not in vtype:
                        raise PolicyValidationError(
                            "%s Query Filter Invalid Value: %s Valid: %s" % (
                                cls.type_name, v, ", ".join(vtype)))
                elif not isinstance(v, vtype):
                    raise PolicyValidationError(
                        "%s Query Filter Invalid Value Type %s" % (
                            cls.type_name, data,))

            filters.append(d)

        return filters


def get_annotation_prefix(s):
    return 'c7n:{}'.format(s)


def merge_dict_list(dict_iter):
    """take an list of dictionaries and merge them.

    last dict wins/overwrites on keys.
    """
    result = {}
    for d in dict_iter:
        result.update(d)
    return result


def merge_dict(a, b):
    """Perform a merge of dictionaries a and b

    Any subdictionaries will be recursively merged.
    Any leaf elements in the form of a list or scalar will use the value from a
    """
    d = {}
    for k, v in a.items():
        if k not in b:
            d[k] = v
        elif isinstance(v, dict) and isinstance(b[k], dict):
            d[k] = merge_dict(v, b[k])
    for k, v in b.items():
        if k not in d:
            d[k] = v
    return d


def select_keys(d, keys):
    result = {}
    for k in keys:
        result[k] = d.get(k)
    return result


def get_human_size(size, precision=2):
    # interesting discussion on 1024 vs 1000 as base
    # https://en.wikipedia.org/wiki/Binary_prefix
    suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    suffixIndex = 0
    while size > 1024:
        suffixIndex += 1
        size = size / 1024.0

    return "%.*f %s" % (precision, size, suffixes[suffixIndex])


def get_support_region(manager):
    # support is a unique service in that it doesnt support regional endpoints
    # thus, we need to construct the client based off the regions found here:
    # https://docs.aws.amazon.com/general/latest/gr/awssupport.html
    #
    # aws-cn uses cn-north-1 for both the Beijing and Ningxia regions
    # https://docs.amazonaws.cn/en_us/aws/latest/userguide/endpoints-Beijing.html
    # https://docs.amazonaws.cn/en_us/aws/latest/userguide/endpoints-Ningxia.html

    partition = get_partition(manager.config.region)
    support_region = None
    if partition == "aws":
        support_region = "us-east-1"
    elif partition == "aws-us-gov":
        support_region = "us-gov-west-1"
    elif partition == "aws-cn":
        support_region = "cn-north-1"
    return support_region


def get_eni_resource_type(eni):
    if eni.get('Attachment'):
        instance_id = eni['Attachment'].get('InstanceId')
    else:
        instance_id = None
    description = eni.get('Description')
    # EC2
    if instance_id:
        rtype = 'ec2'
    # ELB/ELBv2
    elif description.startswith('ELB app/'):
        rtype = 'elb-app'
    elif description.startswith('ELB net/'):
        rtype = 'elb-net'
    elif description.startswith('ELB gwy/'):
        rtype = 'elb-gwy'
    elif description.startswith('ELB'):
        rtype = 'elb'
    # Other Resources
    elif description == 'ENI managed by APIGateway':
        rtype = 'apigw'
    elif description.startswith('AWS CodeStar Connections'):
        rtype = 'codestar'
    elif description.startswith('DAX'):
        rtype = 'dax'
    elif description.startswith('AWS created network interface for directory'):
        rtype = 'dir'
    elif description == 'DMSNetworkInterface':
        rtype = 'dms'
    elif description.startswith('arn:aws:ecs:'):
        rtype = 'ecs'
    elif description.startswith('EFS mount target for'):
        rtype = 'fsmt'
    elif description.startswith('ElastiCache'):
        rtype = 'elasticache'
    elif description.startswith('AWS ElasticMapReduce'):
        rtype = 'emr'
    elif description.startswith('CloudHSM Managed Interface'):
        rtype = 'hsm'
    elif description.startswith('CloudHsm ENI'):
        rtype = 'hsmv2'
    elif description.startswith('AWS Lambda VPC'):
        rtype = 'lambda'
    elif description.startswith('AWS Lambda VPC ENI'):
        rtype = 'lambda'
    elif description.startswith('Interface for NAT Gateway'):
        rtype = 'nat'
    elif (description == 'RDSNetworkInterface' or
            description.startswith('Network interface for DBProxy')):
        rtype = 'rds'
    elif description == 'RedshiftNetworkInterface':
        rtype = 'redshift'
    elif description.startswith('Network Interface for Transit Gateway Attachment'):
        rtype = 'tgw'
    elif description.startswith('VPC Endpoint Interface'):
        rtype = 'vpce'
    elif description.startswith('aws-k8s-branch-eni'):
        rtype = 'eks'
    else:
        rtype = 'unknown'
    return rtype


class C7NJmespathFunctions(functions.Functions):
    @functions.signature(
        {'types': ['string']}, {'types': ['string']}
    )
    def _func_split(self, sep, string):
        return string.split(sep)


class C7NJMESPathParser(Parser):
    def parse(self, expression):
        result = super().parse(expression)
        return ParsedResultWithOptions(
            expression=result.expression,
            parsed=result.parsed
        )


class ParsedResultWithOptions(ParsedResult):
    def search(self, value, options=None):
        # if options are explicitly passed in, we honor those
        if not options:
            options = jmespath.Options(custom_functions=C7NJmespathFunctions())
        return super().search(value, options)


def jmespath_search(*args, **kwargs):
    return jmespath.search(
        *args,
        **kwargs,
        options=jmespath.Options(custom_functions=C7NJmespathFunctions())
    )


def jmespath_compile(expression):
    parsed = C7NJMESPathParser().parse(expression)
    return parsed
