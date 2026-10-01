# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging

from c7n_oci.actions.base import OCIBaseAction


class Failing(OCIBaseAction):

    fail_on_error = False

    def perform_action(self, resource):
        raise ValueError("quota exceeded")


def test_process_logs_the_exception(caplog):
    action = Failing({"type": "failing"})
    action.failed_resources = []
    action.result = {"succeeded_resources": [], "failed_resources": action.failed_resources}
    with caplog.at_level(logging.ERROR, logger="custodian.oci.actions.base"):
        action.process([{"id": "ocid1.instance.x"}])
    assert "Reason: quota exceeded" in caplog.text
    assert "{ex.message}" not in caplog.text
