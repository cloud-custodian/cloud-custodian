# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .aws import AWS
from c7n.query import (
    QueryResourceManager, TypeInfo)
from c7n.utils import local_session
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.resources.shield import IsShieldProtected


# Global accelerator is a AWS global service.US West (N. California) Region
# must be specified in global accelerator api call.
# Please reference this AWS document:
# https://docs.aws.amazon.com/global-accelerator/latest/dg/preserve-client-ip-address.regions.html
GlobalAccelerator_REGION = 'us-west-2'


@AWS.resources.register('globalaccelerator')
class GlobalAccelerator(QueryResourceManager):
    """AWS Global Accelerator

    https://docs.aws.amazon.com/global-accelerator/latest/dg/what-is-global-accelerator.html
    """

    class resource_type(TypeInfo):

        service = 'globalaccelerator'
        enum_spec = ('list_accelerators', 'Accelerators', None)
        detail_spec = (
            'describe_accelerator', 'AcceleratorArn', 'AcceleratorArn', 'Accelerator')
        arn = id = 'AcceleratorArn'
        name = 'Name'
        date = 'CreationTime'
        arn_type = 'accelerator'
        cfn_type = 'AWS::GlobalAccelerator::Accelerator'
        permission_prefix = 'globalaccelerator'

    def augment(self, resources):
        client = self.get_client()

        def _augment(r):
            r['Tags'] = self.retry(client.list_tags_for_resource,
                ResourceArn=r['AcceleratorArn'])['Tags']
            return r
        resources = super().augment(resources)
        return list(map(_augment, resources))

    def get_client(self):
        return local_session(self.session_factory) \
            .client('globalaccelerator', region_name=GlobalAccelerator_REGION)


# When taggingresource api is used in tagging operation, got the error:
# Invocation of TagResources for this resource is not supported in this region.
# This region is us-west-2 since global accelerator is a global service and us-west-2 must be used.
# Therefore additional tag and remove-tag functions are implemented.
@GlobalAccelerator.action_registry.register('tag')
class TagGlobalAccelerator(Tag):
    """Create tags on Global Accelerator

    :example:

    .. code-block:: yaml

        policies:
            - name: globalaccelerator-db-tag
              resource: aws.globalaccelerator
              actions:
                - type: tag
                  key: test
                  value: something
    """
    permissions = ('globalaccelerator:TagResource',)

    def get_client(self):
        return self.manager.get_client()

    def process_resource_set(self, client, resources, new_tags):
        for r in resources:
            try:
                client.tag_resource(ResourceArn=r["AcceleratorArn"], Tags=new_tags)
            except client.exceptions.AcceleratorNotFoundException:
                continue


@GlobalAccelerator.action_registry.register('remove-tag')
class RemoveGlobalAcceleratorTag(RemoveTag):
    """Remove tags from a global accelerator
    :example:

    .. code-block:: yaml

        policies:
            - name: globalaccelerator-remove-tag
              resource: aws.globalaccelerator
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('globalaccelerator:UntagResource',)

    def get_client(self):
        return self.manager.get_client()

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            try:
                client.untag_resource(ResourceArn=r['AcceleratorArn'], TagKeys=tags)
            except client.exceptions.AcceleratorNotFoundException:
                continue


@GlobalAccelerator.action_registry.register('mark-for-op')
class MarkForOpReadinessCheck(TagDelayedAction):

    def get_client(self):
        return self.manager.get_client()


@GlobalAccelerator.filter_registry.register('marked-for-op')
class MarkedForOpReadinessCheck(TagActionFilter):

    def get_client(self):
        return self.manager.get_client()


GlobalAccelerator.filter_registry.register('shield-enabled', IsShieldProtected)
