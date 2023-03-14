# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

# register provider
import c7n_tencentcloud.provider  # noqa


def initialize_tencentcloud():
    # register shared actions & outputs
    import c7n_tencentcloud.filters
    import c7n_tencentcloud.actions
    import c7n_tencentcloud.output  # noqa
