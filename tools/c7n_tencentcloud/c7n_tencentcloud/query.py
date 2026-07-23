# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from retrying import RetryError
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

from c7n.actions import ActionRegistry
from c7n.ctx import ExecutionContext
from c7n.exceptions import PolicyExecutionError
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources
from c7n.utils import local_session, chunks, jmespath_search
from .actions.tags import register_tag_actions, register_tag_filters
from .client import Session

DESC_SOURCE_NAME = "describe-tencentcloud"


class TypeMeta(type):
    """TypeMeta"""

    def __repr__(cls) -> str:
        return f"<Type info service:{cls.service} client:{cls.version}>"


class ResourceTypeInfo(metaclass=TypeMeta):
    """ResourceTypeInfo"""
    # used to construct tencentcloud client
    id: str = ""  # required, the field name to get resource instance id
    endpoint: str = ""
    service: str = ""
    version: str = ""

    # enum_spec: ("action", "jsonpath", "extra_params")
    enum_spec = ()
    paging_def: dir = {}  # define how to do paging
    batch_size: int = 10

    # used by metric filter
    metrics_enabled: bool = False
    metrics_namespace: str = ""
    metrics_batch_size: int = 10

    # metrics_dimension_def: [(target_key_name, original_key_name), ...]
    # target_key_name: used for dimensions.[].name in metric API
    # original_key_name: used to get value to set dimensions.[].value in metric API
    metrics_dimension_def = []
    # the field name for resource id
    # it must be one of the target_key_name in metrics_dimension_def
    metrics_instance_id_name: str = ""

    resource_prefix: str = ""


class ResourceQuery:
    """ResourceQuery"""

    def __init__(self, session_factory: Session) -> None:
        self.session_factory = session_factory

    @staticmethod
    def resolve(resource_type):
        if not isinstance(resource_type, type):
            raise ValueError(resource_type)
        else:
            m = resource_type
        return m

    def filter(self, region: str, resource_type, params: dict):
        """
        The function gets the resource metadata from resource_manger and get the resources
        through client

        :param resource_manager: The resource manager object that is calling the filter
        :param params: dict
        :return: A list of dictionaries.
        """
        cli = self.session_factory.client(resource_type.endpoint,
                                          resource_type.service,
                                          resource_type.version,
                                          region)
        action, jsonpath, extra_params = resource_type.enum_spec
        if extra_params:
            params.update(extra_params)
        try:
            resp = cli.execute_query(action, params)
            return jmespath_search(jsonpath, resp)
        except (RetryError, TencentCloudSDKException) as err:
            raise PolicyExecutionError(err) from err

    def paged_filter(self, region: str, resource_type, params: dict):
        """Paging query resources

        :param resource_manager: The resource manager object that is calling the filter
        :param params: dict
        :return: A list of dictionaries.
        """
        cli = self.session_factory.client(resource_type.endpoint,
                                          resource_type.service,
                                          resource_type.version,
                                          region)
        action, jsonpath, extra_params = resource_type.enum_spec
        if extra_params:
            params.update(extra_params)
        try:
            resp = cli.execute_paged_query(action,
                                           params,
                                           jsonpath,
                                           resource_type.paging_def)
            return resp
        except (RetryError, TencentCloudSDKException) as err:
            raise PolicyExecutionError(err) from err

    def get_resource_tags(self, region: str, qcs_list: []):
        """
        get_resource_tags
        """
        from c7n_tencentcloud.resources.tag import TAG

        tag_resource_type = TAG.resource_type
        params = TAG.get_simple_call_params(qcs_list)
        return self.filter(region, tag_resource_type, params)


@sources.register(DESC_SOURCE_NAME)
class DescribeSource:
    """DescribeSource"""

    def __init__(self, resource_manager) -> None:
        """
        :param query: The query to execute from query in policy.yaml
        """
        self.resource_manager = resource_manager
        self.resource_type = resource_manager.resource_type
        self.region = resource_manager.config.region
        self._session = None
        self.tag_batch_size: int = 9

    _query_helper = None

    @property
    def query_helper(self):
        if self._query_helper is None:
            self._query_helper = ResourceQuery(
                local_session(
                    self.resource_manager.session_factory))
        return self._query_helper

    def resources(self, params=None):
        """
        It returns a list of resources that match the given parameters

        :param params: A dictionary of parameters to filter the list of resources returned
        :return: A list of resources.
        """
        if params is None:
            params = {}

        if self.resource_manager.resource_type.paging_def:
            res = self.query_helper.paged_filter(self.resource_manager.config.region,
                                                 self.resource_manager.resource_type,
                                                 params)
        else:
            res = self.query_helper.filter(self.resource_manager.config.region,
                                           self.resource_manager.resource_type,
                                           params)
        return res

    def get_permissions(self):
        return []

    def get_resource_tag(self, resources):
        """
        Get resource tag
        All resource tags need to be obtained separately
        """
        resource_map = dict(zip(self.get_resource_qcs(resources), resources))

        for batch in chunks(resource_map, self.tag_batch_size):
            # construct a separate id to qcs code map,since we're using unqualified qcs
            # without uin/account id. ideally we could get rid of this if we always have
            # the account id
            tags = self.query_helper.get_resource_tags(self.region, batch)
            for tag in tags:
                if tag['Resource'] not in resource_map:
                    continue
                resource_map[tag['Resource']]['Tags'] = [
                    {'Key': t['TagKey'], 'Value': t['TagValue']} for t in tag['Tags']]
        return resources

    def get_resource_qcs(self, resources):
        """
        get_resource_qcs
        resource description https://cloud.tencent.com/document/product/598/10606
        """
        # qcs::${ServiceType}:${Region}:${Account}:${ResourcePrefix}/${ResourceId}
        # qcs::cvm:ap-singapore::instance/ins-ibu7wp2a
        qcs_list = []
        for r in resources:
            qcs = self.get_qcs(self.resource_type.service,
                               self.region,
                               self.resource_manager.config.account_id,
                               self.resource_type.resource_prefix,
                               r[self.resource_type.id])
            qcs_list.append(qcs)
        return qcs_list

    @staticmethod
    def get_qcs(service, region, account_id, prefix, resource_id):
        """
        get_qcs
        resource description https://cloud.tencent.com/document/product/598/10606
        """
        # qcs::${ServiceType}:${Region}:${Account}:${ResourcePreifx}/${ResourceId}
        # qcs::cvm:ap-singapore::instance/ins-ibu7wp2a
        account_id = f"uin/{account_id}" if account_id else ""
        return f"qcs::{service}:{region}:{account_id}:{prefix}/{resource_id}"


class QueryMeta(type):
    """
    metaclass to have consistent action/filter registry for new resources.
    """

    def __new__(cls, name, parents, attrs):
        if 'filter_registry' not in attrs:
            attrs['filter_registry'] = FilterRegistry(f"{name.lower()}.filters")
        if 'action_registry' not in attrs:
            attrs['action_registry'] = ActionRegistry(f"{name.lower()}%s.actions")

        if attrs['resource_type']:
            m = ResourceQuery.resolve(attrs['resource_type'])
            if getattr(m, 'taggable', True):
                register_tag_actions(attrs['action_registry'])
                register_tag_filters(attrs['filter_registry'])

        return super(QueryMeta, cls).__new__(cls, name, parents, attrs)


class QueryResourceManager(ResourceManager, metaclass=QueryMeta):
    """QueryResourceManager"""

    source_mapping = {'describe': DescribeSource}

    class resource_type(ResourceTypeInfo):
        pass

    def __init__(self, ctx: ExecutionContext, data):
        """
        A constructor for the class.

        :param ctx: ExecutionContext - this is the context of the execution. It contains
        information about the execution, such as the execution ID, the execution status,
        the execution start time, etc
        :type ctx: ExecutionContext
        :param data: one policy configured in the yaml file.
        """
        super().__init__(ctx, data)
        self._session = None
        self.source: DescribeSource = self.get_source(self.source_type)

    @property
    def source_type(self):
        return self.data.get("source", DESC_SOURCE_NAME)

    def get_model(self):
        return self.resource_type

    def get_source(self, source_type):
        factory = self.source_mapping.get(
            source_type in ("describe", DESC_SOURCE_NAME) and "describe",
            sources.get(source_type))
        if factory is None:
            raise ValueError("Invalid source type %s" % source_type)
        return factory(self)

    def get_client(self):
        type_info = self.resource_type
        return self.get_session().client(
            type_info.endpoint,
            type_info.service,
            type_info.version,
            self.config.region)

    def get_session(self):
        return local_session(self.session_factory)

    def get_permissions(self):
        return self.source.get_permissions()

    def get_resource_query_params(self):
        config_query = self.data.get("query", [])
        params = {}
        for it in config_query:
            params.update(it)
        return params

    def resources(self):
        params = self.get_resource_query_params()
        resources = self.source.resources(params)
        resources = self.augment(resources)
        # filter resources
        resources = self.filter_resources(resources)

        self.check_resource_limit(resources)
        return resources

    def augment(self, resources):
        return self.source.get_resource_tag(resources)

    # TODO
    # to support configs: max-resources, max-resources-percent
    def check_resource_limit(self, resources):
        return resources

    def get_metrics_req_params(self, resources):
        """
        return (namespace, instances)
        namespace: something like QCE/CVM
        instances: [
            {"Dimensions": [{"Name": "xxx", "value": "yyy"}, ...]},
            {"Dimensions": [{"Name": "xxx", "value": "yyy"}, ...]},
            ...
        ]
        """
        if not self.resource_type.metrics_dimension_def:
            raise PolicyExecutionError("internal error: invalid metrics config")
        instances = []
        for s in resources:
            dimensions = []
            for item in self.resource_type.metrics_dimension_def:
                dimensions.append({
                    "Name": item[0],
                    "Value": str(s[item[1]])  # force to string
                })
            instances.append({"Dimensions": dimensions})

        return (self.resource_type.metrics_namespace, instances)

    def get_resource_id_from_dimensions(self, dimensions):
        """
        return the resource id in dimension values in metrics data
        dimensions: the Dimensions fields in Cloud Monitor response data
        """
        for item in dimensions:
            if item["Name"] == self.resource_type.metrics_instance_id_name:
                return item["Value"]
        return None
