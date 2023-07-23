# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import importlib
import logging
import os

import oci
from c7n_oci.constants import ENV_FINGERPRINT, ENV_USER, ENV_KEY_FILE, ENV_REGION, ENV_TENANCY

log = logging.getLogger("custodian.oci.session")


class SessionFactory:
    def __init__(self, profile=None):
        self.profile = profile
        self.user_agent_name = "Oracle-CloudCustodian"
        self._config = self._set_oci_config()
        self._authenticate_user()

    def _set_oci_config(self):
        config = None
        if self._check_environment_variables():
            config = {
                "fingerprint": os.environ.get(ENV_FINGERPRINT),
                "key_file": os.environ.get(ENV_KEY_FILE),
                "region": os.environ.get(ENV_REGION),
                "tenancy": os.environ.get(ENV_TENANCY),
                "user": os.environ.get(ENV_USER),
            }
        elif self.profile:
            config = oci.config.from_file(profile_name=self.profile)
        else:
            config = oci.config.from_file()

        config["additional_user_agent"] = (
            f'{self.user_agent_name} {config["additional_user_agent"]}'
            if config.get("additional_user_agent")
            else self.user_agent_name
        )
        return config

    def _check_environment_variables(self):
        return all(
            os.environ.get(env)
            for env in [ENV_FINGERPRINT, ENV_KEY_FILE, ENV_REGION, ENV_TENANCY, ENV_USER]
        )

    def _authenticate_user(self):
        try:
            identity_client = oci.identity.IdentityClient(self._config)
            response = identity_client.get_user(self._config.get("user"))
            log.info(f"Successfully authenticated user [{response.data.name}]")
        except Exception as e:
            log.error("Failed to authenticate user.\nMessage: {}".format(e))

    def __call__(self):
        session = Session(self._config)
        return session


class Session:
    def __init__(self, config):
        self._config = config

    def client(self, client_string):
        service_name, client_name = client_string.rsplit(".", 1)
        service_module = importlib.import_module(service_name)
        client_class = getattr(service_module, client_name)
        client_args = {"config": self._config}
        client = client_class(**client_args)
        return client
