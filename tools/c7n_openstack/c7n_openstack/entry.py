# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
from c7n_openstack.resources import (
    project,
    flavor,
    server,
    user,
    security_group,
    secret
)

log = logging.getLogger('custodian.openstack')

ALL = [
    flavor,
    project,
    server,
    user,
    security_group,
    secret
]


def initialize_openstack():
    """openstack entry point
    """
