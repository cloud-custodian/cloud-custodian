# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.actions import BaseAction


class SnowflakeAction(BaseAction):

    def process(self, resources):
        raise NotImplementedError("Base action class does not implement behavior")
