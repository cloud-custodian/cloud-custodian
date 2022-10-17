# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import json
import os
import pytest
from pathlib import Path

from click.testing import CliRunner

from c7n.config import Config
from c7n.resources import load_resources

try:
    from c7n_left import cli, utils
    from c7n_left.providers.terraform import TerraformProvider

    LEFT_INSTALLED = True
except ImportError:
    pytest.skip(reason="c7n_left not installed", allow_module_level=True)
    LEFT_INSTALLED = False
else:
    load_resources(("terraform.*",))

cur_dir = Path(os.curdir).absolute()
terraform_dir = Path(__file__).parent.parent.parent.parent / "tests" / "terraform"
terraform_dir = terraform_dir.relative_to(cur_dir)


def test_load_policy(test):
    test.load_policy(
        {"name": "check1", "resource": "terraform.aws_s3_bucket"}, validate=True
    )
    test.load_policy(
        {"name": "check2", "resource": ["terraform.aws_s3_bucket"]}, validate=True
    )
    test.load_policy({"name": "check3", "resource": ["terraform.aws_*"]}, validate=True)


def test_load_policy_dir(tmp_path):
    write_output_test_policy(tmp_path)
    policies = utils.load_policies(tmp_path, Config.empty())
    assert len(policies) == 1


def test_provider_parse():
    graph = TerraformProvider().parse(terraform_dir / "ec2_stop_protection_disabled")
    resource_types = list(graph.get_resources_by_type("aws_subnet"))
    rtype, resources = resource_types.pop()
    assert rtype == "aws_subnet"
    assert resources[0]["__tfmeta"] == {
        "filename": "network.tf",
        "line_start": 5,
        "line_end": 8,
        "src_dir": Path("tests") / "terraform" / "ec2_stop_protection_disabled",
    }


def test_multi_resource_policy(tmp_path):
    (tmp_path / "policy.json").write_text(
        json.dumps(
            {
                "policies": [
                    {
                        "name": "check-wild",
                        "resource": "terraform.aws_*",
                    }
                ]
            }
        )
    )
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "run",
            "-p",
            str(tmp_path),
            "-d",
            str(terraform_dir / "aws_lambda_check_permissions"),
            "-o",
            "json",
            "--output-file",
            str(tmp_path / "output.json"),
        ],
    )
    assert result.exit_code == 0
    data = json.loads((tmp_path / "output.json").read_text())
    assert len(data["results"]) == 2


def write_output_test_policy(tmp_path):
    (tmp_path / "policy.json").write_text(
        json.dumps(
            {
                "policies": [
                    {
                        "name": "check-bucket",
                        "resource": "terraform.aws_s3_bucket",
                        "filters": [{"server_side_encryption_configuration": "absent"}],
                    }
                ]
            }
        )
    )


def test_cli_output_rich(tmp_path):
    write_output_test_policy(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "run",
            "-p",
            str(tmp_path),
            "-d",
            str(terraform_dir / "aws_s3_encryption_audit"),
            "-o",
            "cli",
        ],
    )
    assert result.exit_code == 0


def test_cli_output_github(tmp_path):
    write_output_test_policy(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "run",
            "-p",
            str(tmp_path),
            "-d",
            str(terraform_dir / "aws_s3_encryption_audit"),
            "-o",
            "github",
        ],
    )
    assert result.exit_code == 0
    assert result.output == (
        "::error file=tests/terraform/aws_s3_encryption_audit/main.tf line=25 lineEnd=28"
        " title=terraform.aws_s3_bucket - policy:check-bucket::\n"
    )


def test_cli_output_json(tmp_path):
    write_output_test_policy(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "run",
            "-p",
            str(tmp_path),
            "-d",
            str(terraform_dir / "aws_s3_encryption_audit"),
            "-o",
            "json",
            "--output-file",
            str(tmp_path / "output.json"),
        ],
    )
    assert result.exit_code == 0

    results = json.loads((tmp_path / "output.json").read_text())
    assert "results" in results
    assert results["results"] == [
        {
            "code_block": [
                [25, 'resource "aws_s3_bucket" "example_c" {'],
                [26, "  bucket = " '"c7n-aws-s3-encryption-audit-test-c"'],
                [27, '  acl    = "private"'],
                [28, "}"],
            ],
            "file_line_end": 28,
            "file_line_start": 25,
            "file_path": "tests/terraform/aws_s3_encryption_audit/main.tf",
            "policy": {
                "filters": [{"server_side_encryption_configuration": "absent"}],
                "mode": {"type": "terraform-source"},
                "name": "check-bucket",
                "resource": "terraform.aws_s3_bucket",
            },
        }
    ]
