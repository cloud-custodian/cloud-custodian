# Copyright 2018 Capital One Services, LLC
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

from c7n.provider import clouds

import copy
import itertools
import logging
import sys

import boto3

from c7n.credentials import SessionFactory
from c7n.registry import PluginRegistry
from c7n import utils

log = logging.getLogger('custodian.aws')


_profile_session = None


def get_profile_session(options):
    global _profile_session
    if _profile_session:
        return _profile_session

    profile = getattr(options, 'profile', None)
    _profile_session = boto3.Session(profile_name=profile)
    return _profile_session


def _default_region(options):
    marker = object()
    value = getattr(options, 'regions', marker)
    if value is marker:
        return

    if len(value) > 0:
        return

    try:
        options.regions = [get_profile_session(options).region_name]
    except Exception:
        log.warning('Could not determine default region')
        options.regions = [None]

    if options.regions[0] is None:
        log.error('No default region set. Specify a default via AWS_DEFAULT_REGION '
                  'or setting a region in ~/.aws/config')
        sys.exit(1)

    log.debug("using default region:%s from boto" % options.regions[0])


def _default_account_id(options):
    if options.assume_role:
        try:
            options.account_id = options.assume_role.split(':')[4]
            return
        except IndexError:
            pass
    try:
        session = get_profile_session(options)
        options.account_id = utils.get_account_id_from_sts(session)
    except Exception:
        options.account_id = None


@clouds.register('aws')
class AWS(object):

    resource_prefix = 'aws'
    # legacy path for older plugins
    resources = PluginRegistry('resources')

    def initialize(self, options):
        """
        """
        _default_region(options)
        _default_account_id(options)
        return options

    def get_session_factory(self, options):
        return SessionFactory(
            options.region,
            options.profile,
            options.assume_role,
            options.external_id)

    def initialize_policies(self, policy_collection, options):
        """Return a set of policies targetted to the given regions.

        Supports symbolic regions like 'all'. This will automatically
        filter out policies if their being targetted to a region that
        does not support the service. Global services will target a
        single region (us-east-1 if only all specified, else first
        region in the list).

        Note for region partitions (govcloud and china) an explicit
        region from the partition must be passed in.
        """
        from c7n.policy import Policy, PolicyCollection
        policies = []
        service_region_map, resource_service_map = get_service_region_map(
            options.regions, policy_collection.resource_types)

        for p in policy_collection:
            available_regions = service_region_map.get(
                resource_service_map.get(p.resource_type), ())

            # its a global service/endpoint, use user provided region
            # or us-east-1.
            if not available_regions and options.regions:
                candidates = [r for r in options.regions if r != 'all']
                candidate = candidates and candidates[0] or 'us-east-1'
                svc_regions = [candidate]
            elif 'all' in options.regions:
                svc_regions = available_regions
            else:
                svc_regions = options.regions

            for region in svc_regions:
                if available_regions and region not in available_regions:
                    level = ('all' in options.regions and
                             logging.DEBUG or logging.WARNING)
                    # TODO: fixme
                    policy_collection.log.log(
                        level, "policy:%s resources:%s not available in region:%s",
                        p.name, p.resource_type, region)
                    continue
                options_copy = copy.copy(options)
                options_copy.region = str(region)

                if len(options.regions) > 1 or 'all' in options.regions and getattr(
                        options, 'output_dir', None):
                    options_copy.output_dir = (
                        options.output_dir.rstrip('/') + '/%s' % region)
                policies.append(
                    Policy(p.data, options_copy,
                           session_factory=policy_collection.session_factory()))
        return PolicyCollection(policies, options)


def get_service_region_map(regions, resource_types):
    # we're not interacting with the apis just using the sdk meta information.
    session = boto3.Session(
        region_name='us-east-1',
        aws_access_key_id='never',
        aws_secret_access_key='found')
    normalized_types = []
    for r in resource_types:
        if r.startswith('aws.'):
            normalized_types.append(r[4:])
        else:
            normalized_types.append(r)

    resource_service_map = {
        r: clouds['aws'].resources.get(r).resource_type.service
        for r in normalized_types if r != 'account'}
    # support for govcloud and china, we only utilize these regions if they
    # are explicitly passed in on the cli.
    partition_regions = {}
    for p in ('aws-cn', 'aws-us-gov'):
        for r in session.get_available_regions('s3', partition_name=p):
            partition_regions[r] = p

    partitions = ['aws']
    for r in regions:
        if r in partition_regions:
            partitions.append(partition_regions[r])

    service_region_map = {}
    for s in set(itertools.chain(resource_service_map.values())):
        for partition in partitions:
            service_region_map.setdefault(s, []).extend(
                session.get_available_regions(s, partition_name=partition))
    return service_region_map, resource_service_map
