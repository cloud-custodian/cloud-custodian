# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import abc
import importlib

from c7n.registry import PluginRegistry


clouds = PluginRegistry('c7n.providers')


class Provider(metaclass=abc.ABCMeta):
    """Provider Base Class"""

    @abc.abstractproperty
    def display_name(self):
        """display name for the provider in docs"""

    @abc.abstractproperty
    def resources(self):
        """resources registry for this cloud provider"""

    @abc.abstractproperty
    def resource_prefix(self):
        """resource prefix for this cloud provider in policy files."""

    @abc.abstractproperty
    def resource_map(self):
        """resource qualified name to python dotted path mapping."""

    @abc.abstractmethod
    def initialize(self, options):
        """Perform any provider specific initialization
        """

    @abc.abstractmethod
    def initialize_policies(self, policy_collection, options):
        """Perform any initialization of policies.

        Common usage is expanding policy collection for per
        region execution and filtering policies for applicable regions.
        """

    @abc.abstractmethod
    def get_session_factory(self, options):
        """Get a credential/session factory for api usage."""

    @classmethod
    def get_resource_types(cls, resource_types):
        """Return the resource classes for the given type names"""
        resource_classes, not_found = import_resource_classes(
            cls.resource_map, resource_types)
        for r in resource_classes:
            cls.resources.notify(r)
        return resource_classes, not_found


def import_resource_classes(resource_map, resource_types):
    if '*' in resource_types:
        resource_types = list(resource_map)

    mod_map = {}
    rmods = set()
    not_found = set()
    found = []

    for r in resource_types:
        if r not in resource_map:
            not_found.add(r)
            continue
        rmodule, rclass = resource_map[r].rsplit('.', 1)
        rmods.add(rmodule)

    for rmodule in rmods:
        mod_map[rmodule] = importlib.import_module(rmodule)

    for rtype in resource_types:
        if rtype in not_found:
            continue
        rmodule, rclass = resource_map[rtype].rsplit('.', 1)
        r = getattr(mod_map[rmodule], rclass, None)
        if r is None:
            not_found.add(rtype)
        else:
            found.append(r)
    return found, list(not_found)


# nosetests seems to think this function is a test
import_resource_classes.__test__ = False


def resources(cloud_provider=None):
    results = {}
    for cname, ctype in clouds.items():
        if cloud_provider and cname != cloud_provider:
            continue
        for rname, rtype in ctype.resources.items():
            results['%s.%s' % (cname, rname)] = rtype
    return results


def get_resource_class(resource_type):
    if '.' in resource_type:
        provider_name, resource = resource_type.split('.', 1)
    else:
        provider_name, resource = 'aws', resource_type
        resource_type = '%s.%s' % (provider_name, resource_type)

    provider = clouds.get(provider_name)
    if provider is None:
        raise KeyError(
            "Invalid cloud provider: %s" % provider_name)

    if resource_type not in provider.resource_map:
        raise KeyError("Invalid resource: %s for provider: %s" % (
            resource, provider_name))
    factory = provider.resources.get(resource)
    assert factory, "Resource:%s not loaded" % resource_type
    return factory
