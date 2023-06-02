# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from oci.work_requests.models import WorkRequest


# Method to check whether the operations mentioned in the responses are completed or not
def all_operation_completed(work_request_client, responses) -> bool:
    for response in responses:
        work_request_response = work_request_client.get_work_request(
            response.headers["opc-work-request-id"]
        )
        status = getattr(work_request_response.data, "status")
        if (
            status != WorkRequest.STATUS_CANCELED
            and status != WorkRequest.STATUS_FAILED
            and status != WorkRequest.STATUS_SUCCEEDED
        ):
            return False
    return True
