# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .provider import AwsCloudControl  # noqa
from .meta import ResourceFinder


def initialize_awscc():
    """Load aws cloud control provider"""
    ResourceFinder.attach()
