# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

# register provider
from c7n_azure.provider import Azure  # NOQA


# ruff: noqa
def initialize_azure():
    # import execution modes
    import c7n_azure.policy
    import c7n_azure.container_host.modes
    import c7n_azure.output # noqa
