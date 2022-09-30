# Copyright 2020 Kapil Thangavelu
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import shutil
from collections import defaultdict

import pytest
from pytest_terraform import hooks, tf, xdist


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    config.addinivalue_line("markers", "terraform: tests using terraform fixtures")

    cache_dir = config.getoption("dest_tf_plugin")
    if not os.path.exists(cache_dir):
        os.mkdir(cache_dir)
    tf.LazyPluginCacheDir.value = os.path.abspath(cache_dir)

    tf.LazyModuleDir.value = config.getoption("dest_tf_mod_dir") or config.getini(
        "terraform-mod-dir"
    )

    if tf.LazyReplay.value is None:
        tf.LazyReplay.value = config.getoption("dest_tf_replay")

    tf.LazyTfBin.value = config.getoption("dest_tf_binary") or shutil.which("terraform")
    if tf.LazyTfBin.value is None and not tf.LazyReplay.value:
        raise ValueError(
            "pytest-terraform requires terraform binary on PATH or "
            "specified with --tf-binary"
        )

    tf.PytestConfig.value = config

    if config.pluginmanager.hasplugin("xdist"):
        config.pluginmanager.register(xdist.XDistTerraform(config))
        tf.terraform.scope_class_map = d = defaultdict(
            lambda: xdist.ScopedTerraformFixture
        )
        d["function"] = tf.TerraformFixture


def pytest_addhooks(pluginmanager):
    """Register pytest_terraform hooks"""
    pluginmanager.add_hookspecs(hooks)


def pytest_addoption(parser):
    group = parser.getgroup("terraform")
    group.addoption(
        "--tf-binary",
        action="store",
        dest="dest_tf_binary",
        help=("Configure the path to the terraform binary. Default is to search PATH"),
    )
    group.addoption(
        "--tf-replay",
        action="store_true",
        dest="dest_tf_replay",
        help=("Use recorded resources instead of invoking terraform"),
    )
    group.addoption(
        "--tf-mod-dir",
        action="store",
        dest="dest_tf_mod_dir",
        help=("Configue the parent directory to look for terraform modules"),
    )
    group.addoption(
        "--tf-plugin-dir",
        action="store",
        dest="dest_tf_plugin",
        default=".tfcache",
        help=(
            "Use this directory for a terraform plugin cache "
            "Default is to use .tfcache"
        ),
    )

    parser.addini("terraform-mod-dir", "Parent Directory for terraform modules")
