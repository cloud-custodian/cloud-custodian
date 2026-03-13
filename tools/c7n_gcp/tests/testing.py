# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from recorder import PROJECT_ID
from c7n_gcp.client import get_default_project
from c7n.testing import C7N_FUNCTIONAL


def effective_project_id():
    if C7N_FUNCTIONAL:
        return get_default_project()

    return PROJECT_ID
