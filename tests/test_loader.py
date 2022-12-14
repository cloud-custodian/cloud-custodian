# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import os.path
from os import path, mkdir
import json
import tempfile
from textwrap import dedent

import pytest

from c7n import loader
from c7n.exceptions import PolicyValidationError
from c7n.config import Config
from .common import BaseTest


class TestSourceLocator(BaseTest):

    def test_yaml_file(self):

        with tempfile.TemporaryDirectory() as tmpdirname:
            filename = path.join(tmpdirname, "testfile.yaml")
            with open(filename, "w") as f:
                f.write(dedent("""\
                    policies:
                      - name: foo
                        resource: s3

                      # One where name isn't the first element.
                      - resource: ec2
                        name: bar
                    """))
            locator = loader.SourceLocator(filename)
            self.assertEqual(locator.find("foo"), "testfile.yaml:2")
            self.assertEqual(locator.find("bar"), "testfile.yaml:7")
            self.assertEqual(locator.find("non-existent"), "")


class TestDirectoryLoader(BaseTest):
    def test_dir_loader(self):
        dir_loader = loader.DirectoryLoader(Config.empty())
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test', 'resource': 's3'}]}, f
                )
            with open(f"{temp_dir}/policy2.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test2', 'resource': 'ec2'}]}, f
                )
            with open(f"{temp_dir}/policy3.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test3', 'resource': 'ebs'}]}, f
                )
            loaded = dir_loader.load_directory(temp_dir)
            self.assertEqual(len(loaded.policies), 3)
            p_names = []
            for p in loaded.policies:
                p_names.append(p.name)
            self.assertEqual(set(p_names), set(['test', 'test2', 'test3']))

    def test_dir_load_recursive(self):
        dir_loader = loader.DirectoryLoader(Config.empty())
        with tempfile.TemporaryDirectory() as temp_dir:
            mkdir(f"{temp_dir}/layer1")
            with open(f"{temp_dir}/layer1/policy.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test', 'resource': 's3'}]}, f
                )
            mkdir(f"{temp_dir}/layer1/layer2")
            with open(f"{temp_dir}/layer1/layer2/policy2.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test2', 'resource': 'ec2'}]}, f
                )
            with open(f"{temp_dir}/policy.3.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test3', 'resource': 'ebs'}]}, f
                )
            loaded = dir_loader.load_directory(temp_dir)
            self.assertEqual(len(loaded.policies), 3)
            p_names = []
            for p in loaded.policies:
                p_names.append(p.name)
            self.assertEqual(set(p_names), set(['test', 'test2', 'test3']))

    def test_dir_loader_duplicate_keys(self):
        dir_loader = loader.DirectoryLoader(Config.empty())
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test', 'resource': 's3'}]}, f
                )
            with open(f"{temp_dir}/policy2.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'name': 'test', 'resource': 'ec2'}]}, f
                )

            with self.assertRaises(PolicyValidationError):
                dir_loader.load_directory(temp_dir)

    def test_dir_loader_bad_policy(self):
        dir_loader = loader.DirectoryLoader(Config.empty())
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(f"{temp_dir}/policy.yaml", "w+") as f:
                json.dump(
                    {"policies": [{'foo': 'test', 'resource': 's3'}]}, f
                )

            with self.assertRaises(PolicyValidationError):
                dir_loader.load_directory(temp_dir)


@pytest.fixture(name='write_policy')
def _write_policy(tmp_path):
    def write_policy(filename, data):
        full_path = os.path.join(tmp_path, filename)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            json.dump(data, f)

    return write_policy


def test_dir_loader_should_skip_hidden_files(tmp_path, write_policy):
    dir_loader = loader.DirectoryLoader(Config.empty())

    write_policy(
        "policy1.yaml",
        {"policies": [{"name": "good", "resource": "s3"}]},
    )

    # hidden files should be ignored
    write_policy(
        ".hidden.yaml",
        {"policies": [{"name": "bad", "resource": "s3"}]},
    )

    policies = dir_loader.load_directory(tmp_path)

    assert len(policies.policies) == 1
    policy, = policies.policies
    assert policy.name == "good"


def test_dir_loader_should_skip_hidden_folders(tmp_path, write_policy):
    dir_loader = loader.DirectoryLoader(Config.empty())

    write_policy(
        "policy1.yaml",
        {"policies": [{"name": "good", "resource": "s3"}]},
    )

    # hidden folders should not be traversed
    write_policy(
        os.path.join(".hidden-dir", "policy2.yaml"),
        {'policies': [{"name": "three", "resource": "s3"}]},
    )

    # hidden sub folders should not be traversed
    write_policy(
        os.path.join(".hidden-dir", "policy2.yaml"),
        {'policies': [{"name": "three", "resource": "s3"}]},
    )

    policies = dir_loader.load_directory(tmp_path)

    assert len(policies.policies) == 1
    policy, = policies.policies
    assert policy.name == "good"


def test_dir_loader_should_skip_hidden_subfolders(tmp_path, write_policy):
    dir_loader = loader.DirectoryLoader(Config.empty())

    write_policy(
        os.path.join("good-dir", "policy1.yaml"),
        {"policies": [{"name": "good", "resource": "s3"}]},
    )

    # hidden sub folders should not be traversed
    write_policy(
        os.path.join("good-dir", ".hidden-dir", "policy2.yaml"),
        {'policies': [{"name": "three", "resource": "s3"}]},
    )

    policies = dir_loader.load_directory(tmp_path)

    assert len(policies.policies) == 1
    policy, = policies.policies
    assert policy.name == "good"
