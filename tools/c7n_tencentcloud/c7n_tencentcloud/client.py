# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.common_client import CommonClient


class Client:
    """Client"""
    def __init__(self,
                cred: credential.Credential,
                service: str,
                version: str,
                profile: ClientProfile,
                region: str) -> None:
        self._cli = CommonClient(service, version, cred, region, profile)

    def execute_query(self, action: str, params: dict) -> dict:
        """execute_query"""
        return self._cli.call_json(action, params)


class Session:
    """Session"""
    def __init__(self) -> None:
        # just using default get_credentials() method
        # steps: Environment Variable -> profile file -> CVM role
        # for reference: https://github.com/TencentCloud/tencentcloud-sdk-python
        self._cred = credential.DefaultCredentialProvider().get_credentials()

    def client(self,
               endpoint: str,
               service: str,
               version: str,
               region: str) -> Client:
        """client"""
        http_profile = HttpProfile()
        http_profile.endpoint = endpoint

        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        cli = Client(self._cred, service, version, client_profile, region)
        return cli
