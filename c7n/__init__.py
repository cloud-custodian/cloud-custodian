# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#

import jmespath
from functools import partial
from c7n.utils import C7NJmespathFunctions

jmespath.search = partial(
    jmespath.search,
    options=jmespath.Options(
        custom_functions=C7NJmespathFunctions()
    )
)
