# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from functools import partial
from unittest.mock import patch

from gcp_common import BaseTest


class TestRateLimit(BaseTest):
    def test_service_ratelimit_on(self):
        factory = partial(
            self.replay_flight_data(
                "project-get-resource", project_id="cloud-custodian"
            ),
            use_rate_limiter=True,
            quota_max_calls=1,
            quota_period=10,
        )
        with patch(
            "pyrate_limiter.limit_context_decorator.LimitContextDecorator.delayed_acquire",
            return_value=None,
        ) as mock_delay:
            p = self.load_policy(
                {"name": "my-projects", "resource": "gcp.project"},
                session_factory=factory,
            )
            p.resource_manager.get_resource(
                {
                    "resourceName": "//cloudresourcemanager.googleapis.com/"
                    "projects/cloud-custodian"
                }
            )
            assert mock_delay.called

    def test_service_ratelimit_off(self):
        factory = self.replay_flight_data(
            "project-get-resource", project_id="cloud-custodian"
        )

        with patch(
            "pyrate_limiter.limit_context_decorator.LimitContextDecorator.delayed_acquire",
            return_value=None,
        ) as mock_delay:
            p = self.load_policy(
                {"name": "my-projects", "resource": "gcp.project"},
                session_factory=factory,
            )
            p.resource_manager.get_resource(
                {
                    "resourceName": "//cloudresourcemanager.googleapis.com/"
                    "projects/cloud-custodian"
                }
            )
            assert not mock_delay.called
