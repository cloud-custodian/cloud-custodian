import re
from abc import abstractmethod, ABCMeta

from c7n.deprecated import DeprecatedField
from c7n.filters.core import ValueFilter, type_schema


class WafClassicRegionalFilterBase(ValueFilter, metaclass=ABCMeta):
    """Filter a resource based on an associated WAF Classic WebACL using the generic value
    filter. The value passed to the filter will be an instance of WebACL from AWS or an empty
    object ({}) if no ACL is associated. WAF Classic can be associated with an Application
    Load Balancer or an API Gateway REST API Stage.

    https://docs.aws.amazon.com/waf/latest/APIReference/API_wafRegional_WebACL.html

    :example:

    Find all API Gateway Rest stages that don't have waf enabled with at least one rule

    .. code-block:: yaml

            policies:
              - name: filter-waf-value
                resource: aws.rest-stage
                filters:
                  - type: waf-enabled
                    key: Rules
                    value: empty

    """

    associated_cache_key = 'c7n:AssociatedResources'

    schema = type_schema(
        'waf-enabled',
        rinherit=ValueFilter.schema,
        **{
            'web-acl': {'type': 'string'},
            'state': {'type': 'boolean'}
        }
    )

    permissions = (
        'waf-regional:ListWebACLs',
        'waf-regional:GetWebACL',  # for augment
        'waf-regional:ListResourcesForWebACL'  # for finding associated resources
    )

    def __init__(self, data, manager=None):
        super().__init__(data, manager)

        # "legacy" mode matches previous WAF based filters for backwards compatability and is
        # enabled when one of the legacy properties is provided or when no value filter properties
        # are given (none of the legacy properties are required)
        self._is_legacy = (
            'web-acl' in self.data
                or 'state' in self.data
                or len(self.data.keys()) == 1  # only filter "type" is given
        )
        self._cached_web_acls = None

    def _legacy_match(self, resource):
        target_acl = self.data.get('web-acl')
        r_acl = self.get_associated_web_acl(resource)
        state = self.data.get('state', False)

        # WAF is considered enabled if there is an associated WebACL AND that ACL matches the
        # specified target in the filter IF provided
        return (bool(r_acl) and (target_acl is None or target_acl == r_acl['Name'])) == state

    # get the set of web acls we should look through by asking the resource manager for the set
    # based on the scope
    def _get_web_acls(self):
        if self._cached_web_acls is None:
            self._cached_web_acls = self.manager.get_resource_manager('waf-regional').resources(
                # required to get the additional detail needed for this filter (e.g. Rules), but
                # the legacy mode does not require additional detail
                augment=True
            )

        return self._cached_web_acls

    # load the resources the web_acl is attached to and cache them with the web acl
    def _load_associated_resources(self, web_acl, resource_type):
        cache_key = f'{self.associated_cache_key}:{resource_type}'

        if cache_key in web_acl:
            return web_acl[cache_key]

        client = self.manager.session_factory().client('waf-regional')

        resource_arns = client.list_resources_for_web_acl(
            WebACLId=web_acl['WebACLId'],
            ResourceType=resource_type
        ).get('ResourceArns', [])

        web_acl[cache_key] = resource_arns

        return resource_arns

    def get_deprecations(self):
        filter_name = self.data["type"]
        return [
            DeprecatedField(f"{filter_name}.{k}", "Use the value filter attributes instead")
            for k in {'web-acl', 'state'}.intersection(self.data)
        ]

    def get_web_acl_from_associations(self, resource_type, resource_arn):
        for web_acl in self._get_web_acls():
            associated_arns = self._load_associated_resources(web_acl, resource_type)
            if resource_arn in associated_arns:
                return web_acl

        # default empty so we can actually match where no web acl is present
        return {}

    def get_web_acl_by_arn(self, arn):
        web_acls = self._get_web_acls()

        return next(
            filter(lambda acl: acl['WebACLArn'] == arn, web_acls),
            # default empty so we can actually match where no web acl is present
            {}
        )

    def validate(self):
        # only allow legacy behavior or new ValueFilter behavior, not both
        if not self._is_legacy:
            # only validate value filter when not in "legacy" mode
            super(WafClassicRegionalFilterBase, self).validate()

    def process(self, resources, event=None):
        if self._is_legacy:
            return [
                resource for resource in resources
                # call value filter on associated WebACL
                if self._legacy_match(resource)
            ]

        return [
            resource for resource in resources
            # call value filter on associated WebACL
            if self(self.get_associated_web_acl(resource))
        ]

    # Main method used to determine the web acl associated with the given resource - must
    # be overriden in a base class as each resource has a slightly unigue way of getting the
    # associated web acl
    @abstractmethod
    def get_associated_web_acl(self, resource):
        raise NotImplementedError('"get_associated_web_acl" must be overriden')


class WafV2FilterBase(ValueFilter, metaclass=ABCMeta):
    """Filter a resource based on an associated WAFv2 WebACL using the generic value filter. The
    value passed to the filter will be an instance of WebACL from AWS or an empty object ({}) if
    no ACL is associated with the rest stage. WAFv2 can be associated with an Application
    Load Balancer, API Gateway REST API Stage, AppSync GraphQL API, Cognito User Pool, Cloudfront
    Distribution, or App Runner Service.

    https://docs.aws.amazon.com/waf/latest/APIReference/API_WebACL.html

    :example:

    Ensure an API Gateway Rest stage has waf enabled with at least one rule

    .. code-block:: yaml

            policies:
              - name: filter-wafv2-value
                resource: aws.rest-stage
                filters:
                  - type: wafv2-enabled
                    key: Rules
                    value: empty

    """

    cache_key = 'c7n:WebACL'
    associated_cache_key = 'c7n:AssociatedResources'

    schema = type_schema(
        'wafv2-enabled',
        rinherit=ValueFilter.schema,
        **{
            'web-acl': {'type': 'string'},
            'state': {'type': 'boolean'}
        }
    )

    permissions = (
        'wafv2:ListWebACLs',
        'wafv2:GetWebACL',  # for augment
        'wafv2:ListResourcesForWebACL'  # for finding associated regional resources
    )

    def __init__(self, data, manager=None):
        super().__init__(data, manager)

        # "legacy" mode matches previous WAF based filters for backwards compatability and is
        # enabled when one of the legacy properties is provided or when no value filter properties
        # are given (none of the legacy properties are required)
        self._is_legacy = (
            'web-acl' in self.data
                or 'state' in self.data
                or len(self.data.keys()) == 1  # only filter "type" is given
        )
        self._cached_web_acls = None

    def _legacy_match(self, r_acl):
        target_acl = self.data.get('web-acl')
        state = self.data.get('state', False)

        return (
            bool(r_acl)
            and (
                target_acl is None
                or bool(re.match(target_acl, r_acl['Name']))
            )
        ) == state

    # get the set of web acls we should look through by asking the resource manager for the set
    # based on the scope
    def _get_web_acls(self, scope):
        if self._cached_web_acls is None:
            self._cached_web_acls = self.manager.get_resource_manager('wafv2').resources(
                query=dict(Scope=scope),
                # required to get the additional detail needed for this filter (e.g. Rules), but
                # the legacy mode does not require additional detail
                augment=(not self._is_legacy)
            )

        return self._cached_web_acls

    # simple search over the list of web acls matching on the specified attribute, returns
    # None if no match
    def _get_associated_web_acl_by_attr(self, attr_name, attr_value, scope):
        web_acls = self._get_web_acls(scope)

        return next(
            filter(lambda acl: acl[attr_name] == attr_value, web_acls),
            # default empty so we can actually match where no web acl is present
            {}
        )

    # load the resources the web_acl is attached to and cache them with the web acl
    # we only need to do this for REGIONAL web acls as cloudfront holds a reference to
    # web acl
    def _load_associated_resources(self, web_acl, resource_type):
        cache_key = f'{self.associated_cache_key}:{resource_type}'

        if cache_key not in web_acl:
            client = self.manager.session_factory().client('wafv2')

            web_acl[cache_key] = client.list_resources_for_web_acl(
                WebACLArn=web_acl['ARN'],
                ResourceType=resource_type
            ).get('ResourceArns', [])

        return web_acl[cache_key]

    def _get_associated_web_acl_cached(self, resource):
        if self.cache_key not in resource:
            resource[self.cache_key] = self.get_associated_web_acl(resource)

        return resource[self.cache_key]

    def get_deprecations(self):
        filter_name = self.data["type"]
        return [
            DeprecatedField(f"{filter_name}.{k}", "Use the value filter attributes instead")
            for k in {'web-acl', 'state'}.intersection(self.data)
        ]

    # only needed for REGIONAL resources so no scope used as regional is default
    def get_web_acl_from_associations(self, resource_type, resource_arn):
        for web_acl in self._get_web_acls(scope='REGIONAL'):
            associated_arns = self._load_associated_resources(web_acl, resource_type)
            if resource_arn in associated_arns:
                return web_acl

        # default empty so we can actually match where no web acl is present
        return {}

    def get_web_acl_by_arn(self, arn, scope='REGIONAL'):
        return self._get_associated_web_acl_by_attr('ARN', arn, scope)

    def get_web_acl_by_id(self, id, scope='REGIONAL'):
        return self._get_associated_web_acl_by_attr('Id', id, scope)

    def validate(self):
        # only allow legacy behavior or new ValueFilter behavior, not both
        if not self._is_legacy:
            # only validate value filter when not in "legacy" mode
            super(WafV2FilterBase, self).validate()

    def process(self, resources, event=None):
        matched = []
        for resource in resources:
            r_web_acl = self._get_associated_web_acl_cached(resource)

            if self._is_legacy:
                if self._legacy_match(r_web_acl):
                    matched.append(resource)
            # call value filter on associated WebACL
            elif self(r_web_acl):
                matched.append(resource)

        return matched

    # Main method used to determine the web acl associated with the given resource - must
    # be overriden in a base class as each resource has a slightly unigue way of getting the
    # associated web acl
    @abstractmethod
    def get_associated_web_acl(self, resource):
        raise NotImplementedError('"get_associated_web_acl" must be overriden')
