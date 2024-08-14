# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import importlib
import logging
import os

import oci

from c7n_oci.constants import (
    ENV_FINGERPRINT,
    ENV_USER,
    ENV_KEY_FILE,
    ENV_REGION,
    ENV_TENANCY,
)

log = logging.getLogger("custodian.oci.session")


class SessionFactory:
    def __init__(self, profile=None, region=None):
        self.profile = profile
        self.user_agent_name = "Oracle-CloudCustodian"
        self.region = region
        if (
            not os.environ.get('OCI_CLI_AUTH')
            or os.environ.get('OCI_CLI_AUTH') != 'instance_principal'
        ):
            self._config = self._set_oci_config()
        else:
            self._config = {}

        # Override the region value passed in the option
        # For global region value, we will consider the region mentioned in the Config file
        if self.region and self.region != "global":
            self._config["region"] = self.region

    @property
    def config(self):
        return self._config

    def _set_oci_config(self):
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
            for env in [
                ENV_FINGERPRINT,
                ENV_KEY_FILE,
                ENV_REGION,
                ENV_TENANCY,
                ENV_USER,
            ]
        )

    def __call__(self):
        session = Session(self._config)
        return session


class Session:
    def __init__(self, config):
        self._config = config
        self.signer = None

    def client(self, client_string, **kwargs):
        service_name, client_name = client_string.rsplit(".", 1)
        service_module = importlib.import_module(service_name)
        client_class = getattr(service_module, client_name)
        client_args = {"config": self._config, **kwargs}
        if os.environ.get('OCI_CLI_AUTH') == 'instance_principal':
            signer = self.signer or oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            client_args['signer'] = signer
            self._config['tenancy_id'] = signer.tenancy_id
            self._config['region'] = signer.region
            self.signer = signer
        client = client_class(**client_args)
        return client

    def get_config(self):
        return self._config
