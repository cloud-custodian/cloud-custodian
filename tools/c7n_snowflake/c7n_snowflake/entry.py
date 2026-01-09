# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_snowflake.provider import Snowflake  # noqa


def initialize_snowflake():
    import c7n_snowflake.session  # noqa
