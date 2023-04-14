from abc import abstractmethod, ABCMeta

from c7n.filters.core import ValueFilter, type_schema


class WafClassicRegionalFilterBase(ValueFilter, metaclass=ABCMeta):
    """Filter a resource based on an associated WAF Classic WebACL using the generic value
    filter. The value passed to the filter will be an instance of WebACL from AWS or an empty
    object ({}) if no ACL is associated with the rest stage. WAF Classic can be associated with
    an Application Load Balancer or an API Gateway REST API Stage.

    https://docs.aws.amazon.com/waf/latest/APIReference/API_wafRegional_WebACL.html

    :example:

    Ensure an API Gateway Rest stage has waf enabled with at least one rule

    .. code-block:: yaml

            policies:
              - name: filter-waf-value
                resource: aws.rest-stage
                filters:
                  - type: waf
                    key: Rules
                    value: empty

    """

    associated_cache_key = 'c7n:AssociatedResources'

    schema = type_schema('waf', rinherit=ValueFilter.schema)

    permissions = (
        'waf-regional:ListWebACLs',
        'waf-regional:GetWebACL', # for augment
        'waf-regional:ListResourcesForWebACL' # for finding associated resources
    )

    def __init__(self, data, manager=None):
        super().__init__(data, manager)

        self._cached_web_acls = None

    # get the set of web acls we should look through by asking the resource manager for the set
    # based on the scope
    def _get_web_acls(self):
        if self._cached_web_acls is None:
            self._cached_web_acls = self.manager.get_resource_manager('waf-regional').resources(
                # required to get the additional detail needed for this filter (e.g. Rules)
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

    def process(self, resources, event=None):
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
        pass


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
                  - type: wafv2
                    key: Rules
                    value: empty

    """

    cache_key = 'c7n:WebACL'
    associated_cache_key = 'c7n:AssociatedResources'

    schema = type_schema('wafv2', rinherit=ValueFilter.schema)

    permissions = (
        'wafv2:ListWebACLs',
        'wafv2:GetWebACL', # for augment
        'wafv2:ListResourcesForWebACL' # for finding associated regional resources
    )

    def __init__(self, data, manager=None):
        super().__init__(data, manager)

        self._cached_web_acls = None

    # get the set of web acls we should look through by asking the resource manager for the set
    # based on the scope
    def _get_web_acls(self, scope):
        if self._cached_web_acls is None:
            self._cached_web_acls = self.manager.get_resource_manager('wafv2').resources(
                query=dict(Scope=scope),
                # required to get the additional detail needed for this filter (e.g. Rules)
                augment=True
            )

        return self._cached_web_acls

    # simple search over the list of web acls to find one matching by Id, returns None if no match
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

    def process(self, resources, event=None):
        matched = []
        for resource in resources:
            if self.cache_key not in resource:
                resource[self.cache_key] = self.get_associated_web_acl(resource)

            # call value filter on associated WebACL
            if self(resource[self.cache_key]):
                matched.append(resource)

        return matched

    # Main method used to determine the web acl associated with the given resource - must
    # be overriden in a base class as each resource has a slightly unigue way of getting the
    # associated web acl
    @abstractmethod
    def get_associated_web_acl(self, resource):
        pass
