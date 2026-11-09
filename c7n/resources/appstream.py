# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.filters.vpc import NetworkLocation, SecurityGroupFilter, SubnetFilter
from c7n.manager import resources
from c7n import query
from c7n.resolver import ValuesFrom
from c7n.utils import local_session, type_schema


@resources.register("appstream-fleet")
class AppStreamFleet(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "appstream"
        enum_spec = ('describe_fleets', 'Fleets', None)
        arn_type = "fleet"
        arn = "Arn"
        id = "Name"
        name = "Name"
        config_type = cfn_type = "AWS::AppStream::Fleet"
        universal_taggable = object()
        permissions_augment = ("appstream:ListTagsForResource",)
    source_mapping = {
        "describe": query.DescribeWithResourceTags,
    }


@resources.register("appstream-stack")
class AppStreamStack(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "appstream"
        enum_spec = ('describe_stacks', 'Stacks', None)
        arn_type = "stack"
        arn = "Arn"
        id = "Name"
        name = "Name"
        config_type = cfn_type = "AWS::AppStream::Stack"
        universal_taggable = object()
        permissions_augment = ("appstream:ListTagsForResource",)

    source_mapping = {
        "describe": query.DescribeWithResourceTags,
    }


@resources.register("appstream-image-builder")
class AppStreamImageBuilder(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "appstream"
        enum_spec = ('describe_image_builders', 'ImageBuilders', None)
        arn = "Arn"
        id = "Name"
        name = "Name"
        date = "CreatedTime"
        cfn_type = "AWS::AppStream::ImageBuilder"
        universal_taggable = object()
        permissions_augment = ("appstream:ListTagsForResource",)

    source_mapping = {
        "describe": query.DescribeWithResourceTags,
    }


@resources.register("appstream-image")
class AppStreamImage(query.QueryResourceManager):
    """AppStream images owned by the account.

    AWS-provided public base images and images shared into the
    account are excluded.
    """

    class resource_type(query.TypeInfo):
        service = "appstream"
        enum_spec = ('describe_images', 'Images', {'Type': 'PRIVATE'})
        arn = "Arn"
        id = "Name"
        name = "Name"
        date = "CreatedTime"
        universal_taggable = object()
        permissions_augment = ("appstream:ListTagsForResource",)

    source_mapping = {
        "describe": query.DescribeWithResourceTags,
    }


@resources.register("appstream-app-block-builder")
class AppStreamAppBlockBuilder(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "appstream"
        enum_spec = ('describe_app_block_builders', 'AppBlockBuilders', None)
        arn = "Arn"
        id = "Name"
        name = "Name"
        date = "CreatedTime"
        config_type = cfn_type = "AWS::AppStream::AppBlockBuilder"
        universal_taggable = object()
        permissions_augment = ("appstream:ListTagsForResource",)

    source_mapping = {
        "describe": query.DescribeWithResourceTags,
    }


@resources.register("appstream-app-block")
class AppStreamAppBlock(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "appstream"
        enum_spec = ('describe_app_blocks', 'AppBlocks', None)
        arn = "Arn"
        id = "Name"
        name = "Name"
        date = "CreatedTime"
        cfn_type = "AWS::AppStream::AppBlock"
        universal_taggable = object()
        permissions_augment = ("appstream:ListTagsForResource",)

    source_mapping = {
        "describe": query.DescribeWithResourceTags,
    }


@resources.register("appstream-application")
class AppStreamApplication(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "appstream"
        enum_spec = ('describe_applications', 'Applications', None)
        arn = "Arn"
        id = "Name"
        name = "Name"
        date = "CreatedTime"
        config_type = cfn_type = "AWS::AppStream::Application"
        universal_taggable = object()
        permissions_augment = ("appstream:ListTagsForResource",)

    source_mapping = {
        "describe": query.DescribeWithResourceTags,
    }


@resources.register("appstream-user")
class AppStreamUser(query.QueryResourceManager):
    """AppStream user pool users.

    User pool users authenticate directly against AppStream rather than
    through a SAML identity provider.

    :example:

    .. code-block:: yaml

        policies:
          - name: appstream-user-pool-users
            resource: aws.appstream-user
            filters:
              - Enabled: true
    """

    class resource_type(query.TypeInfo):
        service = "appstream"
        enum_spec = ('describe_users', 'Users', {'AuthenticationType': 'USERPOOL'})
        arn = "Arn"
        id = "UserName"
        name = "UserName"
        date = "CreatedTime"
        cfn_type = "AWS::AppStream::User"


class AppStreamSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "VpcConfig.SubnetIds[]"


class AppStreamSecurityGroupFilter(SecurityGroupFilter):

    RelatedIdsExpression = "VpcConfig.SecurityGroupIds[]"


for klass in (AppStreamFleet, AppStreamImageBuilder, AppStreamAppBlockBuilder):
    klass.filter_registry.register('subnet', AppStreamSubnetFilter)
    klass.filter_registry.register('security-group', AppStreamSecurityGroupFilter)
    klass.filter_registry.register('network-location', NetworkLocation)


@AppStreamImage.filter_registry.register('cross-account')
class AppStreamImageCrossAccount(CrossAccountAccessFilter):
    """Filter images shared with accounts outside the allowed list.

    :example:

    .. code-block:: yaml

        policies:
          - name: appstream-image-cross-account
            resource: aws.appstream-image
            filters:
              - type: cross-account
                whitelist:
                  - '123456789012'
    """

    schema = type_schema(
        'cross-account',
        whitelist_from=ValuesFrom.schema,
        whitelist={'type': 'array', 'items': {'type': 'string'}})
    permissions = ('appstream:DescribeImagePermissions',)
    annotation_key = 'c7n:CrossAccountViolations'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('appstream')
        allowed_accounts = set(self.get_accounts())
        results = []
        for r in resources:
            if r.get('ImageSharedWithOthers') == 'FALSE':
                continue
            try:
                shared = self.manager.retry(
                    client.describe_image_permissions,
                    Name=r['Name']).get('SharedImagePermissionsList', ())
            except client.exceptions.ResourceNotFoundException:
                continue
            violations = [
                s['sharedAccountId'] for s in shared
                if s['sharedAccountId'] not in allowed_accounts]
            if violations:
                r[self.annotation_key] = violations
                results.append(r)
        return results
