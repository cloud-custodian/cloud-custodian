# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import os
from pathlib import Path
import sys
import time
from unittest.mock import MagicMock

from click.testing import CliRunner
import pytest

from c7n.config import Bag


try:
    from c7n_left import cli
    from c7n_left import test as left_test

    LEFT_INSTALLED = True
except ImportError:
    pytest.skip(reason="c7n_left not installed", allow_module_level=True)
    LEFT_INSTALLED = False


data_dir = Path(os.curdir).absolute() / "data"


def test_test_reporter_discovery(capsys):
    reporter = left_test.TestReporter(None, Bag(output_file=sys.stdout))
    runner = Bag(unmatched_policies=[1], policies=[2, 3], unmatched_tests=[1])

    reporter.on_tests_discovered(runner, [1])
    captured = capsys.readouterr()
    assert "Discovered 1 Tests" in captured.out


def test_test_reporter_result():
    reporter = left_test.TestReporter(None, Bag(output_file=sys.stdout))
    console = MagicMock()
    reporter.console = console

    def get_test_result():
        return {
            "success": False,
            "stat_checks": 3,
            "stat_used": 2,
            "stat_unmatched": 1,
            "unmatched": [],
            "name": "some-test",
            "unused": [],
        }

    reporter.on_test_result(Bag(get_test_result=get_test_result))
    assert console.print.call_count == 2


def test_test_reporter_complete():
    reporter = left_test.TestReporter(None, Bag(output_file=sys.stdout))
    console = MagicMock()
    reporter.console = console

    reporter.start_time = time.time()
    reporter.failures = 2
    reporter.total = 3

    reporter.on_tests_complete()
    console.print.assert_called_once()


def test_cli_no_tests(tmp_path):
    (tmp_path / "policy.yaml").write_text(
        """
        policies:
          - name: "check-wild"
            resource: "terraform.aws_*"
        """
    )

    test_case_dir = tmp_path / "tests" / "check-wild"
    test_case_dir.mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(cli.cli, ["test", "-p", str(tmp_path)])
    assert result.exit_code == 0
    assert "Discovered 0 Tests - 1/1 Policies Untested" in result.stdout


def test_cli_test_assertion_not_used(tmp_path):
    (tmp_path / "policy.yaml").write_text(
        """
        policies:
          - name: "check-wild"
            resource: "terraform.google_*"
        """
    )
    test_case_dir = tmp_path / "tests" / "check-wild"
    test_case_dir.mkdir(parents=True)
    (test_case_dir / "gcp.tf").write_text(
        """
        resource "google_pubsub_topic" "example" {
          name = "example-topic"
          labels = {
            foo = "bar"
          }
          message_retention_duration = "86600s"
        }
        """
    )

    (test_case_dir / "left.plan.yaml").write_text(
        """
        - "resource.__tfmeta.path": "google_pubsub_topic.example"
        - "resource.__tfmeta.path": "google_pubsub_topic.example2"
        """
    )

    runner = CliRunner()
    result = runner.invoke(cli.cli, ["test", "-p", str(tmp_path)], catch_exceptions=False)
    assert result.exit_code == 1
    assert "Unused Checks" in result.output
    assert "example2" in result.output


def test_cli_test_finding_not_asserted(tmp_path):
    (tmp_path / "policy.yaml").write_text(
        """
        policies:
          - name: "check-wild"
            resource: "terraform.google_*"
        """
    )
    test_case_dir = tmp_path / "tests" / "check-wild"
    test_case_dir.mkdir(parents=True)
    (test_case_dir / "gcp.tf").write_text(
        """
        resource "google_pubsub_topic" "example" {
          name = "example-topic"
          labels = {
            foo = "bar"
          }
          message_retention_duration = "86600s"
        }
        """
    )

    (test_case_dir / "left.plan.yaml").write_text(
        """
        []
        """
    )

    runner = CliRunner()
    result = runner.invoke(cli.cli, ["test", "-p", str(tmp_path)], catch_exceptions=False)
    assert result.exit_code == 1
    assert "1 findings unmatched" in result.output
    assert "google_pubsub_topic.example" in result.output


def test_cli_test_success(tmp_path):
    (tmp_path / "policy.yaml").write_text(
        """
        policies:
          - name: "check-wild"
            resource: "terraform.aws_*"
        """
    )

    test_case_dir = tmp_path / "tests" / "check-wild"
    test_case_dir.mkdir(parents=True)
    (test_case_dir / "gcp.tf").write_text(
        """
        resource "google_pubsub_topic" "example" {
          name = "example-topic"
          labels = {
            foo = "bar"
          }
          message_retention_duration = "86600s"
        }
        """
    )

    (test_case_dir / "aws.tf").write_text(
        """
        resource "aws_sqs_queue" "terraform_queue" {
          name                        = "terraform-example-queue.fifo"
          fifo_queue                  = true
          content_based_deduplication = true
        }
        """
    )

    (test_case_dir / "left.plan.yaml").write_text(
        """
        - "resource.__tfmeta.filename": "aws.tf"
        """
    )

    runner = CliRunner()
    result = runner.invoke(cli.cli, ["test", "-p", str(tmp_path)], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Discovered 1 Tests" in result.output
    assert "Success check-wild - 1 checks" in result.output
