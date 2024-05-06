# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import os

import socket
from retrying import retry

from c7n import version
from .utils import PageMethod
from c7n.exceptions import PolicyExecutionError
from c7n.utils import jmespath_search
from requests.exceptions import ConnectionError
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.common_client import CommonClient

RETRYABLE_EXCEPTIONS = (socket.error, ConnectionError)


def retry_exception(exception):
    return isinstance(exception, RETRYABLE_EXCEPTIONS)


def retry_result(resp):
    real_resp = resp.get("Response", {})
    err = real_resp.get("Error", None)
    if err:
        return err["Code"].find("RequestLimitExceeded") >= 0
    return False


class Client:
    """
    Client is a wrapper for the CommonClient class.
    About CommonClient:
        https://cloud.tencent.com/document/sdk/Python Comment Client section
    """
    MAX_REQUEST_TIMES = 100
    MAX_RESPONSE_DATA_COUNT = 10000

    def __init__(self,
                 cred: credential.Credential,
                 service: str,
                 version: str,
                 profile: ClientProfile,
                 region: str) -> None:
        self._cli = CommonClient(service, version, cred, region, profile)

    @retry(retry_on_exception=retry_exception,
           retry_on_result=retry_result,
           wait_exponential_multiplier=100,
           wait_exponential_max=1000,
           stop_max_attempt_number=5)
    def execute_query(self, action: str, params: dict) -> dict:
        """
        Call the client method and get the resources.

        :param action: The name of the action to be performed
        :param params: dict, query conditions, resources have different definition,
            need to refer to SDK documents.
        :return: A dictionary
        """
        self._cli._sdkVersion = "Custodian-v" + version.version
        resp = self._cli.call_json(action, params)
        return resp

    def execute_paged_query(self, action: str, params: dict,
                            jsonpath: str, paging_def: dict) -> list:
        """
        Call the client method and get the resource, the paging query is automatically filled.
        """
        results = []
        paging_method = paging_def["method"]

        if paging_method == PageMethod.Offset:
            params[PageMethod.Offset.name] = 0
            params[paging_def["limit"]["key"]] = paging_def["limit"]["value"]
        elif paging_method == PageMethod.PaginationToken:
            params[PageMethod.PaginationToken.name] = ""
            pagination_token_path = paging_def.get("pagination_token_path", "")
            if not pagination_token_path:
                raise PolicyExecutionError("config to use pagination_token but not set token path")
            params[paging_def["limit"]["key"]] = paging_def["limit"]["value"]
        elif paging_method == PageMethod.Page:
            params[PageMethod.Page.name] = 1
            params[paging_def["limit"]["key"]] = paging_def["limit"]["value"]
        else:
            raise PolicyExecutionError("unsupported paging method")

        query_counter = 1
        while True:
            if (query_counter > self.MAX_REQUEST_TIMES
                    or len(results) > self.MAX_RESPONSE_DATA_COUNT):
                raise PolicyExecutionError("get too many resources from cloud provider")

            # some api Offset and Limit fields are string
            if paging_method == PageMethod.Offset and isinstance(paging_def["limit"]["value"], str):
                params[PageMethod.Offset.name] = str(params[PageMethod.Offset.name])

            result = self.execute_query(action, params)
            query_counter += 1
            items = jmespath_search(jsonpath, result)
            if len(items) > 0:
                results.extend(items)
                if paging_method == PageMethod.Offset:
                    if len(items) < int(paging_def["limit"]["value"]):
                        # no more data
                        break
                    params[PageMethod.Offset.name] = int(params[PageMethod.Offset.name]) + \
                                                     int(paging_def["limit"]["value"])
                elif paging_method == PageMethod.Page:
                    if len(items) < int(paging_def["limit"]["value"]):
                        # no more data
                        break
                    params[paging_method.name] = int(params[paging_method.name]) + 1
                else:
                    token = jmespath_search(pagination_token_path, result)
                    if token == "":
                        break
                    params[PageMethod.PaginationToken.name] = str(token)
            else:
                break
        return results


class Session:
    """Session"""

    def __init__(self) -> None:
        """
        credential_file contains secret_id and secret_key.
        the file content format likes:
            {"TENCENTCLOUD_AK":"", "TENCENTCLOUD_SK":""}
        """
        # just using default get_credentials() method
        # steps: Environment Variable -> profile file -> CVM role
        # for reference: https://github.com/TencentCloud/tencentcloud-sdk-python

        cred_provider = credential.DefaultCredentialProvider()

        # the DefaultCredentialProvider does not handle sts assumed role sessions
        # so we need to check for the token first
        if 'TENCENTCLOUD_TOKEN' in os.environ:
            if (
                    'TENCENTCLOUD_SECRET_ID' not in os.environ or
                    'TENCENTCLOUD_SECRET_KEY' not in os.environ
            ):
                raise TencentCloudSDKException(
                    'TENCENTCLOUD_TOKEN provided, but one of TENCENTCLOUD_SECRET_ID'
                    'or TENCENTCLOUD_SECRET_KEY missing'
                )
            cred = credential.Credential(
                secret_id=os.environ['TENCENTCLOUD_SECRET_ID'],
                secret_key=os.environ['TENCENTCLOUD_SECRET_KEY'],
                token=os.environ['TENCENTCLOUD_TOKEN']
            )
            cred_provider.cred = cred

        self._cred = cred_provider.get_credentials()

    @property
    def secret_id(self):
        return self._cred.secret_id

    @property
    def secret_key(self):
        return self._cred.secret_key

    @property
    def token(self):
        return self._cred.token

    def client(self,
               endpoint: str,
               service: str,
               version: str,
               region: str) -> Client:
        """client"""
        http_profile = HttpProfile()

        # use regional endpoint, instead of roundtripping to centralized one.
        # in practice this can greatly reduce latency on roundtrips
        if region:
            parts = endpoint.split('.')
            parts.insert(1, region)
            endpoint = '.'.join(parts)

        http_profile.endpoint = endpoint
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile

        cli = Client(self._cred, service, version, client_profile, region)

        return cli
