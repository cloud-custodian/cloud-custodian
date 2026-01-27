# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re
import datetime
from datetime import timedelta
from dateutil.tz import tzutc

import itertools
import logging

from concurrent.futures import as_completed

from c7n.actions import BaseAction
from c7n.exceptions import ClientError, PolicyValidationError
from c7n.filters import (
    AgeFilter, ValueFilter, Filter, CrossAccountAccessFilter)
from c7n.manager import resources
from c7n.query import QueryResourceManager, DescribeSource, TypeInfo
from c7n.resolver import ValuesFrom
from c7n.utils import (
    local_session,
    type_schema,
    chunks,
    merge_dict_list,
    parse_date,
    jmespath_compile
)
from c7n import deprecated


log = logging.getLogger('custodian.ami')


class DescribeImageSource(DescribeSource):

    def get_resources(self, ids, cache=True):
        while ids:
            try:
                return super(DescribeImageSource, self).get_resources(ids, cache)
            except ClientError as e:
                bad_ami_ids = ErrorHandler.extract_bad_ami(e)
                if bad_ami_ids:
                    for b in bad_ami_ids:
                        ids.remove(b)
                    continue
                raise
        return []


@resources.register('ami')
class AMI(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'ec2'
        arn_type = 'image'
        enum_spec = (
            'describe_images', 'Images', None)
        id = 'ImageId'
        filter_name = 'ImageIds'
        filter_type = 'list'
        name = 'Name'
        date = 'CreationDate'
        id_prefix = "ami-"

    source_mapping = {
        'describe': DescribeImageSource
    }

    def resources(self, query=None):
        if query is None and 'query' in self.data:
            query = merge_dict_list(self.data['query'])
        elif query is None:
            query = {}
        if query.get('Owners') is None:
            query['Owners'] = ['self']
        return super(AMI, self).resources(query=query)


class ErrorHandler:

    @staticmethod
    def extract_bad_ami(e):
        """Handle various client side errors when describing images"""
        msg = e.response['Error']['Message']
        error = e.response['Error']['Code']
        e_ami_ids = None
        if error == 'InvalidAMIID.NotFound':
            e_ami_ids = [
                e_ami_id.strip() for e_ami_id
                in msg[msg.find("'[") + 2:msg.rfind("]'")].split(',')]
            log.warning("Image not found %s" % e_ami_ids)
        elif error == 'InvalidAMIID.Malformed':
            e_ami_ids = [msg[msg.find('"') + 1:msg.rfind('"')]]
            log.warning("Image id malformed %s" % e_ami_ids)
        return e_ami_ids


@AMI.action_registry.register('deregister')
class Deregister(BaseAction):
    """Action to deregister AMI

    To prevent deregistering all AMI, it is advised to use in conjunction with
    a filter (such as image-age)

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-deregister-old
                resource: ami
                filters:
                  - type: image-age
                    days: 90
                actions:
                  - deregister
    """

    schema = type_schema('deregister', **{'delete-snapshots': {'type': 'boolean'}})
    permissions = ('ec2:DeregisterImage',)
    snap_expr = jmespath_compile('BlockDeviceMappings[].Ebs.SnapshotId')

    def process(self, images):
        client = local_session(self.manager.session_factory).client('ec2')
        image_count = len(images)
        images = self.filter_resources(images, 'OwnerId', self.manager.ctx.options.account_id)
        if len(images) != image_count:
            self.log.info("Implicitly filtered %d non owned images", image_count - len(images))

        for i in images:
            self.manager.retry(client.deregister_image, ImageId=i['ImageId'])

            if not self.data.get('delete-snapshots'):
                continue
            snap_ids = self.snap_expr.search(i) or ()
            for s in snap_ids:
                try:
                    self.manager.retry(client.delete_snapshot, SnapshotId=s)
                except ClientError as e:
                    if e.response['Error']['Code'] == 'InvalidSnapshot.InUse':
                        continue


@AMI.action_registry.register('set-deprecation')
class SetDeprecation(BaseAction):
    """Action to enable or disable AMI deprecation

    To prevent deprecation of all AMIs, it is advised to use in conjunction with
    a filter (such as image-age)

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-deprecate-old
                resource: ami
                filters:
                  - type: image-age
                    days: 30
                actions:
                  - type: set-deprecation
                    #Number of days from AMI creation
                    age: 90
                    #Number of days from now
                    #days: 90
                    #Specific date/time
                    #date: "2023-11-30"

    """

    schema = type_schema(
        'set-deprecation',
        date={'type': 'string'},
        days={'type': 'integer'},
        age={'type': 'integer'})
    permissions = ('ec2:EnableImageDeprecation', 'ec2:DisableImageDeprecation')
    dep_date = None
    dep_age = None

    def validate(self):
        try:
            if 'date' in self.data:
                self.dep_date = parse_date(self.data.get('date'))
                if not self.dep_date:
                    raise PolicyValidationError(
                        "policy:%s filter:%s has invalid date format" % (
                            self.manager.ctx.policy.name, self.type))
            elif 'days' in self.data:
                self.dep_date = (datetime.datetime.now(tz=tzutc()) +
                    timedelta(days=int(self.data.get('days'))))
            elif 'age' in self.data:
                self.dep_age = (int(self.data.get('age')))
        except (ValueError, OverflowError):
            raise PolicyValidationError(
                "policy:%s filter:%s has invalid time interval" % (
                    self.manager.ctx.policy.name, self.type))

    def process(self, images):
        client = local_session(self.manager.session_factory).client('ec2')
        image_count = len(images)
        images = self.filter_resources(images, 'OwnerId', self.manager.ctx.options.account_id)
        if len(images) != image_count:
            self.log.info("Implicitly filtered %d non owned images", image_count - len(images))
        for i in images:
            if not self.dep_date and not self.dep_age:
                self.manager.retry(client.disable_image_deprecation, ImageId=i['ImageId'])
            else:
                if self.dep_age:
                    date = parse_date(i['CreationDate']) + timedelta(days=self.dep_age)
                else:
                    date = self.dep_date
                # Hack because AWS won't let you set a deprecation time in the
                # past - set to now + 1 minute if the time is in the past
                if date < datetime.datetime.now(tz=tzutc()):
                    odate = str(date)
                    date = datetime.datetime.now(tz=tzutc()) + timedelta(minutes=1)
                    log.warning("Deprecation time %s is in the past for Image %s.  Setting to %s.",
                        odate, i['ImageId'], date)
                self.manager.retry(client.enable_image_deprecation,
                    ImageId=i['ImageId'], DeprecateAt=date)


@AMI.action_registry.register('remove-launch-permissions')
class RemoveLaunchPermissions(BaseAction):
    """Action to remove the ability to launch an instance from an AMI

    DEPRECATED - use set-permissions instead to support AWS Organizations
    sharing as well as adding permissions

    This action will remove any launch permissions granted to other
    AWS accounts from the image, leaving only the owner capable of
    launching it

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-stop-share-old
                resource: ami
                filters:
                  - type: image-age
                    days: 60
                actions:
                  - type: remove-launch-permissions

    """
    deprecations = (
        deprecated.action("use set-permissions instead with 'remove' attribute"),
    )
    schema = type_schema(
        'remove-launch-permissions',
        accounts={'oneOf': [
            {'enum': ['matched']},
            {'type': 'string', 'minLength': 12, 'maxLength': 12}]})

    permissions = ('ec2:ResetImageAttribute', 'ec2:ModifyImageAttribute',)

    def validate(self):
        if 'accounts' in self.data and self.data['accounts'] == 'matched':
            found = False
            for f in self.manager.iter_filters():
                if isinstance(f, AmiCrossAccountFilter):
                    found = True
                    break
            if not found:
                raise PolicyValidationError(
                    "policy:%s filter:%s with matched requires cross-account filter" % (
                        self.manager.ctx.policy.name, self.type))

    def process(self, images):
        client = local_session(self.manager.session_factory).client('ec2')
        for i in images:
            self.process_image(client, i)

    def process_image(self, client, image):
        accounts = self.data.get('accounts')
        if not accounts:
            return client.reset_image_attribute(
                ImageId=image['ImageId'], Attribute="launchPermission")
        if accounts == 'matched':
            accounts = image.get(AmiCrossAccountFilter.annotation_key)
        if not accounts:
            return
        remove = []
        if 'all' in accounts:
            remove.append({'Group': 'all'})
            accounts.remove('all')
        remove.extend([{'UserId': a} for a in accounts if not a.startswith('arn:')])
        if not remove:
            return
        client.modify_image_attribute(
            ImageId=image['ImageId'],
            LaunchPermission={'Remove': remove},
            OperationType='remove')


@AMI.action_registry.register('cancel-launch-permission')
class CancelLaunchPermissions(BaseAction):
    """Action to cancel this account's access to another another account's shared AMI

    If another AWS account shares an image with your account, and you
    no longer want to allow its use in your account, this action will
    remove the permission for your account to laucnh from the image.

    As this is not reversible without accessing the AMI source account, it defaults
    to running in dryrun mode. Set dryrun to false to enforce.

    Note this does not apply to AMIs shared by Organization or OU.
    https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/cancel-sharing-an-AMI.html

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-cancel-share-to-me-old
                resource: ami
                query:
                  - ExecutableUsers: [self]
                  - Owners: []
                filters:
                  - type: image-age
                    days: 90
                actions:
                  - type: cancel-launch-permission

    """
    schema = type_schema('cancel-launch-permission', dryrun={'type': 'boolean'})

    permissions = ('ec2:CancelImageLaunchPermission',)

    def process(self, images):
        client = local_session(self.manager.session_factory).client('ec2')
        for i in images:
            self.process_image(client, i)

    def process_image(self, client, image):
        client.cancel_image_launch_permission(
            ImageId=image['ImageId'],
            DryRun=self.data.get('dryrun', True))


@AMI.action_registry.register('set-permissions')
class SetPermissions(BaseAction):
    """Set or remove AMI launch permissions

    This action will add or remove launch permissions granted to other
    AWS accounts, organizations or organizational units from the image.

    Use the 'add' and 'remove' parameters to control which principals
    to add or remove, respectively.  The default is to remove any permissions
    granted to other AWS accounts.  Principals can be an AWS account id,
    an organization ARN, or an organizational unit ARN

    Use 'remove: matched' in combination with the 'cross-account' filter
    for more flexible removal options such as preserving access for a set of
    whitelisted accounts:

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-share-remove-cross-account
                resource: ami
                filters:
                  - type: cross-account
                    whitelist:
                      - '112233445566'
                      - 'arn:aws:organizations::112233445566:organization/o-xxyyzzaabb'
                      - 'arn:aws:organizations::112233445566:ou/o-xxyyzzaabb/ou-xxyy-aabbccdd'
                actions:
                  - type: set-permissions
                    remove: matched
                # To remove all permissions
                # - type: set-permissions
                # To remove public permissions
                # - type: set-permissions
                #   remove:
                #     - all
                # To remove specific permissions
                # - type: set-permissions
                #   remove:
                #     - '223344556677'
                #     - 'arn:aws:organizations::112233445566:organization/o-zzyyxxbbaa'
                #     - 'arn:aws:organizations::112233445566:ou/o-zzyyxxbbaa/ou-xxyy-ddccbbaa'
                # To set specific permissions
                # - type: set-permissions
                #   remove: matched
                #   add:
                #     - '223344556677'
                #     - 'arn:aws:organizations::112233445566:organization/o-zzyyxxbbaa'
                #     - 'arn:aws:organizations::112233445566:ou/o-zzyyxxbbaa/ou-xxyy-ddccbbaa'
    """

    schema = type_schema(
        'set-permissions',
        remove={'oneOf': [
            {'enum': ['matched']},
            {'type': 'array', 'items': {'type': 'string'}}
        ]},
        add={'type': 'array', 'items': {'type': 'string'}}
    )

    permissions = ('ec2:ResetImageAttribute', 'ec2:ModifyImageAttribute',)

    def validate(self):
        if self.data.get('remove') == 'matched':
            found = False
            for f in self.manager.iter_filters():
                if isinstance(f, AmiCrossAccountFilter):
                    found = True
                    break
            if not found:
                raise PolicyValidationError(
                    "policy:%s filter:%s with matched requires cross-account filter" % (
                        self.manager.ctx.policy.name, self.type))

    def process(self, images):
        client = local_session(self.manager.session_factory).client('ec2')
        for i in images:
            self.process_image(client, i)

    def process_image(self, client, image):
        to_add = self.data.get('add')
        to_remove = self.data.get('remove')
        # Default is to remove all permissions
        if not to_add and not to_remove:
            return client.reset_image_attribute(
                ImageId=image['ImageId'], Attribute="launchPermission")
        remove = []
        add = []
        account_regex = re.compile('\\d{12}')
        # https://docs.aws.amazon.com/organizations/latest/APIReference/API_Organization.html
        org_regex = re.compile(
            r'arn:[a-zA-Z-]+:organizations::\d{12}:organization\/o-[a-z0-9]{10,32}'
        )
        # https://docs.aws.amazon.com/organizations/latest/APIReference/API_OrganizationalUnit.html
        ou_regex = re.compile(
            r'arn:[a-zA-Z-]+:organizations::\d{12}:ou\/o-[a-z0-9]{10,32}\/ou-[0-9a-z]{4,32}-[0-9a-z]{8,32}'
        )
        if to_remove:
            if 'all' in to_remove:
                remove.append({'Group': 'all'})
                to_remove.remove('all')
            if to_remove == 'matched':
                to_remove = image.get(AmiCrossAccountFilter.annotation_key)
            if to_remove:
                principals = [v for v in to_remove if account_regex.match(v)]
                if principals:
                    remove.extend([{'UserId': a} for a in principals])
                principals = [v for v in to_remove if org_regex.match(v)]
                if principals:
                    remove.extend([{'OrganizationArn': a} for a in principals])
                principals = [v for v in to_remove if ou_regex.match(v)]
                if principals:
                    remove.extend([{'OrganizationalUnitArn': a} for a in principals])

        if to_add:
            if 'all' in to_add:
                add.append({'Group': 'all'})
                to_add.remove('all')
            if to_add:
                principals = [v for v in to_add if account_regex.match(v)]
                if principals:
                    add.extend([{'UserId': a} for a in principals])
                principals = [v for v in to_add if org_regex.match(v)]
                if principals:
                    add.extend([{'OrganizationArn': a} for a in principals])
                principals = [v for v in to_add if ou_regex.match(v)]
                if principals:
                    add.extend([{'OrganizationalUnitArn': a} for a in principals])

        if remove:
            self.manager.retry(client.modify_image_attribute,
                ImageId=image['ImageId'],
                LaunchPermission={'Remove': remove},
                OperationType='remove')

        if add:
            self.manager.retry(client.modify_image_attribute,
                ImageId=image['ImageId'],
                LaunchPermission={'Add': add},
                OperationType='add')


@AMI.action_registry.register('copy')
class Copy(BaseAction):
    """Action to copy AMIs with optional encryption

    This action can copy AMIs while optionally encrypting or decrypting
    the target AMI. It is advised to use in conjunction with a filter.

    Note there is a max in flight of 5 per account/region.

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-ensure-encrypted
                resource: ami
                filters:
                  - type: value
                    key: encrypted
                    value: true
                actions:
                  - type: copy
                    encrypt: true
                    key-id: 00000000-0000-0000-0000-000000000000
    """

    permissions = ('ec2:CopyImage',)
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['copy']},
            'name': {'type': 'string'},
            'description': {'type': 'string'},
            'region': {'type': 'string'},
            'encrypt': {'type': 'boolean'},
            'key-id': {'type': 'string'}
        }
    }

    def process(self, images):
        session = local_session(self.manager.session_factory)
        client = session.client(
            'ec2',
            region_name=self.data.get('region', None))

        for image in images:
            client.copy_image(
                Name=self.data.get('name', image['Name']),
                Description=self.data.get('description', image['Description']),
                SourceRegion=session.region_name,
                SourceImageId=image['ImageId'],
                Encrypted=self.data.get('encrypt', False),
                KmsKeyId=self.data.get('key-id', ''))


@AMI.filter_registry.register('image-age')
class ImageAgeFilter(AgeFilter):
    """Filters images based on the age (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-remove-launch-permissions
                resource: ami
                filters:
                  - type: image-age
                    days: 30
    """

    date_attribute = "CreationDate"
    schema = type_schema(
        'image-age',
        op={'$ref': '#/definitions/filters_common/comparison_operators'},
        days={'type': 'number', 'minimum': 0})


@AMI.filter_registry.register('image-ancestry')
class ImageAncestryFilter(Filter):
    """Filters images based on parent owner using GetImageAncestry API

    Flags AMIs that don't have an approved owner in their ancestry chain.
    max_depth defaults to 1 (immediate parent). Set to 2 to include grandparent, etc.

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-non-approved-parent
                resource: ami
                filters:
                  - type: image-ancestry
                    approved_owners:
                      - '123456789012'
                      - amazon
                    max_depth: 2
    """

    schema = type_schema(
        'image-ancestry',
        approved_owners={'type': 'array', 'items': {'type': 'string'}},
        max_depth={'type': 'integer', 'minimum': 1},
        required=['approved_owners'])

    def get_permissions(self):
        return ['ec2:DescribeImages', 'ec2:GetImageAncestry']

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ec2')
        approved_owners = self.data['approved_owners']
        results = []

        for r in resources:            
            if self._check_parent_owner(client, r):
                results.append(r)

        return results

    def _check_parent_owner(self, client, resource):
        approved_owners = self.data['approved_owners']
        # Check if the AMI itself is from an approved owner
        ami_owner = resource.get('ImageOwnerAlias') or resource.get('OwnerId')
        if ami_owner in self.data['approved_owners']:
            return False  # AMI is approved, skip ancestry check

        if 'c7n:image-ancestry' not in resource:
            try:
                ancestry = client.get_image_ancestry(ImageId=resource['ImageId'])
                resource['c7n:image-ancestry'] = ancestry.get('ImageAncestryEntries', [])
            except ClientError as e:
                log.warning(f"Error getting ancestry for {r['ImageId']}: {e}")
                resource['c7n:image-ancestry'] = []
        ancestry = resource['c7n:image-ancestry']
        max_depth = self.data.get('max_depth', 1)
        
        # Check ancestors up to max_depth
        for depth in range(min(max_depth, len(ancestry))):
            parent_entry = ancestry[depth]
            parent_id = parent_entry.get('ImageId')
            
            if not parent_id:
                continue
            
            # Skip if we already looked up the owner
            if 'OwnerId' in parent_entry or 'ImageOwnerAlias' in parent_entry:
                owner = parent_entry.get('ImageOwnerAlias') or parent_entry.get('OwnerId')
                if owner in approved_owners:
                    return False
                continue
            
            try:
                resp = client.describe_images(
                    ImageIds=[parent_id],
                    IncludeDeprecated=True,
                    IncludeDisabled=True
                )
                if not resp.get('Images'):
                    continue
                
                parent_image = resp['Images'][0]
                owner = parent_image.get('ImageOwnerAlias') or parent_image.get('OwnerId')
                
                # Cache the owner info in the ancestry entry
                parent_entry['OwnerId'] = parent_image.get('OwnerId')
                if parent_image.get('ImageOwnerAlias'):
                    parent_entry['ImageOwnerAlias'] = parent_image['ImageOwnerAlias']
                
                if owner in approved_owners:
                    return False
            except ClientError as e:
                if e.response['Error']['Code'] != 'InvalidAMIID.NotFound':
                    log.warning(f"Error describing parent image {parent_id}: {e}")
                continue
        
        # No approved ancestor found, flag this AMI
        return True


@AMI.filter_registry.register('unused')
class ImageUnusedFilter(Filter):
    """Filters images based on usage

    true: image has no instances spawned from it
    false: image has instances spawned from it

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-unused
                resource: ami
                filters:
                  - type: unused
                    value: true
    """

    schema = type_schema('unused', value={'type': 'boolean'})

    def get_permissions(self):
        return list(itertools.chain(*[
            self.manager.get_resource_manager(m).get_permissions()
            for m in ('asg', 'launch-config', 'ec2')]))

    def _pull_asg_images(self):
        asgs = self.manager.get_resource_manager('asg').resources()
        image_ids = set()
        lcfgs = set(a['LaunchConfigurationName'] for a in asgs if 'LaunchConfigurationName' in a)
        lcfg_mgr = self.manager.get_resource_manager('launch-config')

        if lcfgs:
            image_ids.update([
                lcfg['ImageId'] for lcfg in lcfg_mgr.resources()
                if lcfg['LaunchConfigurationName'] in lcfgs])

        tmpl_mgr = self.manager.get_resource_manager('launch-template-version')
        for tversion in tmpl_mgr.get_resources(
                list(tmpl_mgr.get_asg_templates(asgs).keys())):
            image_ids.add(tversion['LaunchTemplateData'].get('ImageId'))
        return image_ids

    def _pull_ec2_images(self):
        ec2_manager = self.manager.get_resource_manager('ec2')
        return {i['ImageId'] for i in ec2_manager.resources()}

    def process(self, resources, event=None):
        images = self._pull_ec2_images().union(self._pull_asg_images())
        if self.data.get('value', True):
            return [r for r in resources if r['ImageId'] not in images]
        return [r for r in resources if r['ImageId'] in images]


@AMI.filter_registry.register('cross-account')
class AmiCrossAccountFilter(CrossAccountAccessFilter):

    schema = type_schema(
        'cross-account',
        # white list accounts
        whitelist_from=ValuesFrom.schema,
        whitelist={'type': 'array', 'items': {'type': 'string'}})

    permissions = ('ec2:DescribeImageAttribute',)
    annotation_key = 'c7n:CrossAccountViolations'

    def process_resource_set(self, client, accounts, resource_set):
        results = []
        for r in resource_set:
            attrs = self.manager.retry(
                client.describe_image_attribute,
                ImageId=r['ImageId'],
                Attribute='launchPermission')['LaunchPermissions']
            r['c7n:LaunchPermissions'] = attrs
            image_accounts = {
                a.get('Group') or a.get('UserId') or
                a.get('OrganizationArn') or a.get('OrganizationalUnitArn')
                for a in attrs
            }
            delta_accounts = image_accounts.difference(accounts)
            if delta_accounts:
                r[self.annotation_key] = list(delta_accounts)
                results.append(r)
        return results

    def process(self, resources, event=None):
        results = []
        client = local_session(self.manager.session_factory).client('ec2')
        accounts = self.get_accounts()
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for resource_set in chunks(resources, 20):
                futures.append(
                    w.submit(
                        self.process_resource_set, client, accounts, resource_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception checking cross account access \n %s" % (
                            f.exception()))
                    continue
                results.extend(f.result())
        return results


@AMI.filter_registry.register('image-attribute')
class ImageAttribute(ValueFilter):
    """AMI Image Value Filter on a given image attribute.

    Filters AMI's with the given AMI attribute

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-unused-recently
                resource: ami
                filters:
                  - type: image-attribute
                    attribute: lastLaunchedTime
                    key: "Value"
                    op: gte
                    value_type: age
                    value: 30
    """

    valid_attrs = (
        'description',
        'kernel',
        'ramdisk',
        'launchPermissions',
        'productCodes',
        'blockDeviceMapping',
        'sriovNetSupport',
        'bootMode',
        'tpmSupport',
        'uefiData',
        'lastLaunchedTime',
        'imdsSupport'
    )

    schema = type_schema(
        'image-attribute',
        rinherit=ValueFilter.schema,
        attribute={'enum': valid_attrs},
        required=('attribute',))
    schema_alias = False

    def get_permissions(self):
        return ('ec2:DescribeImageAttribute',)

    def process(self, resources, event=None):
        attribute = self.data['attribute']
        self.get_image_attribute(resources, attribute)
        return [resource for resource in resources
                if self.match(resource['c7n:attribute-%s' % attribute])]

    def get_image_attribute(self, resources, attribute):
        client = local_session(
            self.manager.session_factory).client('ec2')

        for resource in resources:
            image_id = resource['ImageId']
            fetched_attribute = self.manager.retry(
                client.describe_image_attribute,
                ImageId=image_id,
                Attribute=attribute)
            keys = set(fetched_attribute) - {'ResponseMetadata', 'ImageId'}
            resource['c7n:attribute-%s' % attribute] = fetched_attribute[keys.pop()]
