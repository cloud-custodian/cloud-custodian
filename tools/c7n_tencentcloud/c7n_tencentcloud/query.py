# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import jmespath
from c7n.utils import local_session
from retrying import RetryError

from .actions.tags import register_tag_actions, register_tag_filters
from .client import Session
from c7n.actions import ActionRegistry
from c7n.ctx import ExecutionContext
from c7n.exceptions import PolicyExecutionError
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException


DESC_SOURCE_NAME = "describe-tencentcloud"


class TypeMeta(type):
    """TypeMeta"""
    def __repr__(cls) -> str:
        return f"<Type info service:{cls.service} client:{cls.version}>"


class ResourceTypeInfo(metaclass=TypeMeta):
    """ResourceTypeInfo"""
    # used to construct tencentcloud client
    id: str = ""  # requried, the field name to get resource instance id
    endpoint: str = ""
    service: str = ""
    version: str = ""

    # enum_spec: ("action", "jsonpath", "extra_params")
    enum_spec = ()
    paging_def: dir = {}  # define how to do paging
    batch_size: int = 10

    # used by metric filter
    metrics_namespace: str = ""
    metrics_batch_size: int = 10
    metrics_instance_id_name: str = ""  # the field name to set resource instance id

    resource_preifx: str = ""


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
            return jmespath.search(jsonpath, resp)
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

    def get_resource_tags(self, region: str, resource6_name: str):
        """
        get_resource_tags
        """
        from c7n_tencentcloud.resources.tag import TAG

        tag_resource_type = TAG.resource_type
        params = TAG.get_simple_call_params(resource6_name)
        return self.filter(region, tag_resource_type, params)


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
        return sources.get(source_type)(self)

    def get_session(self):
        if self._session is None:
            self._session = local_session(self.session_factory)
        return self._session

    def get_permissions(self):
        return self.source.get_permissions()

    def get_resource_query_params(self):
        config_query = self.data.get("query", [])
        if config_query:
            return {
                "Filters": config_query
            }
        else:
            return {}

    def resources(self):
        params = self.get_resource_query_params()
        resources = self.source.resources(params)

        # filter resoures
        resources = self.filter_resources(resources)

        self.check_resource_limit(resources)
        return resources

    def augment(self, resources):
        return resources

    # TODO
    # to support configs: max-resources, max-resources-percent
    def check_resource_limit(self, resources):
        return resources


@sources.register(DESC_SOURCE_NAME)
class DescribeSource:
    """DescribeSource"""
    def __init__(self, resource_manager: QueryResourceManager) -> None:
        """
        :param query: The query to execute from query in policy.yaml
        """
        self.resource_manager = resource_manager
        self.resource_type = resource_manager.resource_type
        self.region = resource_manager.config.region
        self.query_helper = ResourceQuery(resource_manager.session_factory)
        self._session = None

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
        self.augment(res)
        return res

    def get_permissions(self):
        return []

    def augment(self, resources):
        for r in resources:
            r["Tags"] = self.get_resource_tag(r)
        return resources

    def get_resource_tag(self, resource):
        """
        Get resource tag
        All resource tags need to be obtained separately
        """
        result = []
        resouce_id = resource[self.resource_type.id]
        ce6 = self.get_resource_qcs(resouce_id)
        res = self.query_helper.get_resource_tags(self.region, ce6)
        if res:
            # get the resource's tags
            for tag in res[0]["Tags"]:
                result.append({
                    "Key": tag["TagKey"],
                    "Value": tag["TagValue"]
                })
        return result

    def get_resource_qcs(self, resource_id):
        """
        get_resource_qcs
        resource description https://cloud.tencent.com/document/product/598/10606
        """
        # qcs::${ServiceType}:${Region}:${Account}:${ResourcePreifx}/${ResourceId}
        # qcs::cvm:ap-singapore::instance/ins-ibu7wp2a
        return "qcs::{}:{}::{}/{}".format(
            self.resource_type.service,
            self.region,
            self.resource_type.resource_preifx,
            resource_id)
