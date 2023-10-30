# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os
import socket
import configparser

from typing import Union
from retrying import retry
from .utils import PageMethod
from c7n.exceptions import PolicyExecutionError
from c7n.utils import jmespath_search
from requests.exceptions import ConnectionError
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.common_client import CommonClient
from tencentcloud.common.credential import STSAssumeRoleCredential, CVMRoleCredential, Credential


RETRYABLE_EXCEPTIONS = (socket.error, ConnectionError)


def retry_exception(exception):
    return isinstance(exception, RETRYABLE_EXCEPTIONS)


def retry_result(resp):
    real_resp = resp.get("Response", {})
    err = real_resp.get("Error", None)
    if err:
        return err["Code"].find("RequestLimitExceeded") >= 0
    return False


def profile_handle(
        profile: str,
        cred_path=os.path.join(os.path.expanduser('~'), '.tencentcloud/credentials')
) -> Union[STSAssumeRoleCredential, Credential]:
    """
        params:
            profile: the profile name
            profile_path: the profile path, deafult path is '~/tencentcloud/credentials'
        des:
            support use profile to auth account and multi-account
        credentials details:
            ```
                [default] (if 'source_profile' is default, this is required!)
                secret_id:xxxx
                secret_key:xxxx
                [profile]
                role_arn: xxx (required)
                session_name: xxx (default is 'custodian-job')
                duration_seconds: 3600 (default is 3600)
                source_profile: xxx (required, must be in ('default', 'cvm_metadata'))
            ```
            parms:
                source_profile: the auth method
                    default: use ak/sk to assume role
                        secret_id: secret_id
                        secket_key: secket_key
                    cvm_metadata: use cvm role to assume role
    """
    if not os.path.exists(cred_path):
        raise TencentCloudSDKException(f'not find the cred path by "{cred_path}"')

    parser = configparser.ConfigParser()
    parser.read(cred_path)
    try:
        profile_obj = parser[profile]
    except KeyError:
        raise TencentCloudSDKException(f'not find profile: {profile}, please check the porfile')

    # if not find role_arn the profile is ak/sk'profile
    role_arn = profile_obj.get('role_arn', None)
    if role_arn is None:
        secret_id = profile_obj.get('secret_id')
        secret_key = profile_obj.get('secret_key')
        token = profile_obj.get('token')

        return Credential(secret_id, secret_key, token)

    session_name = profile_obj.get('session_name', 'tencentcloud-session')
    duration_seconds = profile_obj.get('duration_seconds', 7200)
    source_profile = profile_obj.get('source_profile')

    # if the source_profile == 'cvm_metadata', you need add the role to cvm
    # and the role must have assume the the role permmission
    if source_profile == 'cvm_metadata':
        cred = CVMRoleCredential()
        common_client = CommonClient(
            credential=cred, region="ap-guangzhou", version='2018-08-13', service="sts")
        params = {
            "RoleArn": role_arn,
            "RoleSessionName": session_name,
            "DurationSeconds": duration_seconds
        }
        rsp = common_client.call_json("AssumeRole", params)
        token = rsp["Response"]["Credentials"]["Token"]
        secret_id = rsp["Response"]["Credentials"]["TmpSecretId"]
        secret_key = rsp["Response"]["Credentials"]["TmpSecretKey"]

        return Credential(secret_id, secret_key, token=token)
    else:
        try:
            sp_obj = parser[source_profile]
        except KeyError:
            raise TencentCloudSDKException(
                f'not find source_profile: {source_profile}, please check the source_profile')

        secret_id = sp_obj.get('secret_id')
        secret_key = sp_obj.get('secret_key')
        token = sp_obj.get('token')

        return STSAssumeRoleCredential(
            secret_id, secret_key, role_arn, session_name, duration_seconds)


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
                    params[PageMethod.Offset.name] = int(params[PageMethod.Offset.name]) +\
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
    def __init__(self, profile: str = None) -> None:
        """
        credential_file contains secret_id and secret_key.
        the file content format likes:
            {"TENCENTCLOUD_AK":"", "TENCENTCLOUD_SK":""}
        """
        # just using default get_credentials() method
        # steps: Environment Variable -> profile file -> CVM role
        # for reference: https://github.com/TencentCloud/tencentcloud-sdk-python

        self.profile = profile

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

        # add profile suport
        if self.profile is not None:
            cred_provider = profile_handle(profile=profile)

        self._cred = cred_provider.get_credentials()

    def __call__(self):
        return self

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
