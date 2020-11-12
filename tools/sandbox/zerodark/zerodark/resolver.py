# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import ipaddress
import sqlite3

from .utils import row_factory


class IPResolver:
    """Resolve as much info as we can about a given ip.

    Typically this is a two level lookup.
     - ip address -> eni info
     - eni info -> resource info (w/ app)

    On failure to lookup eni info we consider some additional possibilities:
     - aws service ip
     - TODO: lookup in vpc/subnet tables.
    """

    # TODO: needs region and account id in queries
    resource_query = {
        'ec2': 'select * from ec2 where instance_id = ?',
        'elb': 'select * from elbs where name = ?'}

    def __init__(self, ipdb_path, cmdb_path, aws_cidrs_path=None):
        self.ipdb = ipdb_path and sqlite3.connect(ipdb_path) or None
        if self.ipdb:
            self.ipdb.row_factory = row_factory
            self.ipdb_cursor = self.ipdb.cursor()

        self.cmdb = cmdb_path and sqlite3.connect(cmdb_path) or None
        if self.cmdb:
            self.cmdb.row_factory = row_factory
            self.cmdb_cursor = self.cmdb.cursor()

        # TODO see if we can do some ip caching
        self.resource_cache = {}

        # Service -> list of service cidrs
        self.aws_cidrs = {}
        if not aws_cidrs_path:
            return

        with open(aws_cidrs_path) as fh:
            ipranges = json.load(fh)
            for r in ipranges.get('prefixes', ()):
                if r['service'] in ('S3', 'AMAZON'):
                    self.aws_cidrs.setdefault(
                        r['service'].lower(), []).append(
                            ipaddress.IPv4Network(r['ip_prefix']))

    def resolve(self, ips, start, end):
        results = {}
        if not self.ipdb:
            return results

        for ip in ips:
            # TODO: see if we need to expand the time window
            # the use of config for ip info creates some lag
            # on capture, and also some potential gaps for
            # short lived resources.
            self.ipdb_cursor.execute(
                '''select * from enis
                   where ip_address = ?
                     and start < ?
                     and (end > ? or end is null)''',
                (ip, end.strftime('%Y-%m-%dT%H:%M'),
                 start.strftime('%Y-%m-%dT%H:%M')))
            info = list(self.ipdb_cursor)
            # TODO: assert on number of records found
            if info:
                eni_info = info.pop()
            # TODO: this a bit speculative wrt to ip usage
            # specific to an enterprise network setup, where in
            # non resolved ips are typically aws services via
            # classic vpc endpoints using public ips. Might need
            # to revisit. also potentially an option on ip string
            # prefix match as a sanity base.
            elif not info:
                n = ipaddress.IPv4Address(str(ip))
                found = False
                for service, cidr_set in self.aws_cidrs.items():
                    for cidr in cidr_set:
                        if n in cidr:
                            results[ip] = {'app': 'aws s3', 'env': 'aws s3'}
                            found = True
                            break
                        if found:
                            break
                    if found:
                        break
                continue
            results[ip] = self.resolve_resource(eni_info)
        return results

    def resolve_resource(self, eni_info):
        # TODO region, account id in cache key
        ri = self.resource_cache.get(eni_info['resource_type'])
        if ri is not None:
            return ri
        service_query = self.resource_query.get(eni_info['resource_id'])
        if service_query is None:
            return eni_info
        self.cmdb_cursor.execute(service_query, (eni_info['resource_type'],))
        ri = self.cmdb_cursor.fetchone()
        if ri is not None:
            ri['type'] = eni_info['resource_id']
            return ri
        else:
            return eni_info
