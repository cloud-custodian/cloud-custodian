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
    DEFAULT_PROFILE,
)

log = logging.getLogger("custodian.oci.session")


class Session:
    def __init__(self, config_file_path=None, profile_name=DEFAULT_PROFILE):
        self.config = None
        self.authenticated = False
        self.config_file_path = config_file_path
        self.profile_name = profile_name

    def initialize_session(self):
        if self.authenticated:
            return
        if os.environ.get(ENV_FINGERPRINT) is not None:
            self.config = {
                "fingerprint": os.environ.get(ENV_FINGERPRINT),
                "key_file": os.environ.get(ENV_KEY_FILE),
                "region": os.environ.get(ENV_REGION),
                "tenancy": os.environ.get(ENV_TENANCY),
                "user": os.environ.get(ENV_USER),
            }
        elif self.profile_name is not None and self.config_file_path is None:
            self.config = oci.config.from_file(profile_name=self.profile_name)
        elif self.profile_name is None and self.config_file_path is not None:
            self.config = oci.config.from_file(self.config_file_path)
        elif self.profile_name and self.config_file_path:
            self.config = oci.config.from_file(self.config_file_path, self.profile_name)
        else:
            self.config = oci.config.from_file()

        self.config["additional_user_agent"] = (
            f'Oracle-CloudCustodian {self.config["additional_user_agent"]}'
            if self.config.get("additional_user_agent")
            else "Oracle-CloudCustodian"
        )

        # The next statements are just to verify that the config is working
        try:
            identity_client = oci.identity.IdentityClient(self.config)

            response = identity_client.get_user(self.config.get("user"))
            self.authenticated = True
            log.info(f"Successfully authenticated user [{response.data.name}]")
        except Exception as e:
            log.error("Failed to authenticate.\nMessage: {}".format(e))

    def get_oci_config(self):
        return self.config

    def client(self, client):
        self.initialize_session()
        service_name, client_name = client.rsplit(".", 1)
        svc_module = importlib.import_module(service_name)
        klass = getattr(svc_module, client_name)

        client_args = {"config": self.config}
        client = klass(**client_args)
        return client

    def get_monitoring_client(self):
        """Creates and returns the MonitoringClient which is used for the Cross-Service querying

        Returns:
              object: MonitoringClient object to make call to Monitoring service
        """
        self.initialize_session()
        svc_module = importlib.import_module("oci.monitoring")
        klass = getattr(svc_module, "MonitoringClient")
        client_args = {"config": self.config}
        client = klass(**client_args)
        return client

    def get_work_request_client(self):
        """Creates WorkRequestClient which is used to check the status of the submitted
           asynchronous job

        Returns:
            object: WorkRequestClient object to check the status of the submitted job
        """
        self.initialize_session()
        svc_module = importlib.import_module("oci.work_requests")
        klass = getattr(svc_module, "WorkRequestClient")
        client_args = {"config": self.config}
        client = klass(**client_args)
        return client
