# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
from pathlib import Path


def load_build():
    path = Path(__file__).parent.parent / "build.py"
    spec = importlib.util.spec_from_file_location("c7n_awscc_build", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_index_maps_service_names(tmp_path):
    # codestarnotifications has no boto3 client of that name, the service
    # map has to translate it to codestar-notifications
    (tmp_path / "aws_codestarnotifications_notificationrule.json").write_text(
        json.dumps(
            {
                "typeName": "AWS::CodeStarNotifications::NotificationRule",
                "handlers": {"read": {"permissions": []}},
            }
        )
    )
    stats = load_build().build_index(tmp_path)
    index = json.loads((tmp_path / "index.json").read_text())
    assert stats["noservice"] == 0
    assert "awscc.codestarnotifications_notificationrule" in index["resources"]
    assert index["augment"]["AWS::CodeStarNotifications::NotificationRule"] == {
        "service": "codestar-notifications",
        "type": "codestarnotifications_notificationrule",
    }
