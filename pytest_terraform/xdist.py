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
import sys

from pytest_terraform import tf
from pytest_terraform.lock import lock_create, lock_delete


class ScopedTerraformFixture(tf.TerraformFixture):
    # specialized terraform fixture for use with
    # non function scopes, that is tracked for xdist
    # teardown, and locked around create/destroy

    state_dir = None
    wid = None
    _AutoTearDown = False

    def create(self, request, module_dir):
        if self.replay:
            super().create(request, module_dir)

        with lock_create(self.state_dir / self.name) as (success, result):
            if success:
                print(
                    "%s create %s - success: %s" % (self.wid, self.name, success),
                    file=sys.stderr,
                )
                tf_test_api = super(ScopedTerraformFixture, self).create(
                    request, module_dir
                )
                result.write(self.runner.work_dir.encode("utf8"))
                return tf_test_api
            return tf.TerraformTestApi.load(
                os.path.join(self.resolve_module_dir(), "tf_resources.json")
            )

    def tear_down(self):
        # print('%s %s fix teardown' % (self.wid, self.name), file=sys.stderr)
        with lock_delete(self.state_dir / self.name) as success:
            #  print('%s %s teardown state:%s' % (
            #        self.wid, self.name, success), file=sys.stderr)
            if not success:
                return
            work_dir = (self.state_dir / self.name).read_text("utf8")
            print(
                "%s teardown %s work-dir %s" % (self.wid, self.name, success),
                file=sys.stderr,
            )
            super(ScopedTerraformFixture)
            runner = self.get_runner(self.resolve_module_dir(), work_dir)
            runner.destroy()


class XDistTerraform(object):

    # Hooks
    # https://github.com/pytest-dev/pytest-xdist/blob/master/src/xdist/newhooks.py

    def __init__(self, config):
        self.config = config
        self.state_dir = None
        self.wid = None

        self.fixture_map = None  # only on worker nodes
        self.tracked_fixtures = set()  # only on worker nodes
        self.completed = set()  # only on worker nodes
        self.test_log = None  # read only fh on worker nodes, append fh on master
        self.activity = []

        if hasattr(self.config, "workerinput"):
            self.wid = self.config.workerinput["workerid"]
        else:
            self.wid = "master"

        if not getattr(self.config, "_tmpdirhandler", None):
            print("eeek %s" % self.wid)

        basetemp = self.config._tmpdirhandler.getbasetemp()
        if self.wid == "master":
            self.state_dir = basetemp.mkdir("terraform")
        else:
            self.state_dir = basetemp / ".." / "terraform"

        ScopedTerraformFixture.state_dir = self.state_dir
        ScopedTerraformFixture.wid = self.wid

        log_path = str(self.state_dir / "completed-log.txt")
        # print(log_path)
        if self.wid == "master":
            self.test_log_writer = open(log_path, mode="ab+", buffering=0)
        # make available to master for self unit testing
        self.test_log_reader = open(log_path, mode="r")

    def generate_fixture_map(self, items):
        fixture_map = {}
        for i in items:
            for f in i.fixturenames:
                if f in self.tracked_fixtures:
                    fixture_map.setdefault(f, set()).add(i.nodeid)
        return fixture_map

    # worker hooks
    def pytest_collection_modifyitems(self, session, config, items):
        """write out the collections of fixtures -> test ids

        in xdist this is only called from the workers
        """
        self.tracked_fixtures = {
            t.name
            for t in tf.terraform.get_fixtures()
            if isinstance(t, ScopedTerraformFixture)
        }
        self.fixture_map = self.generate_fixture_map(items)

    def pytest_runtest_teardown(self, item, nextitem):
        found = []
        for f in item.fixturenames:
            if f in self.tracked_fixtures:
                found.append(f)
        if not found:
            return
        # print(
        #    '%s worker teardown found: %s item used:%s tracked:%s' % (
        #    self.wid, found, item.fixturenames, self.tracked_fixtures), file=sys.stderr)

        completed = {n.strip() for n in self.test_log_reader.readlines()}
        self.completed.update(completed)
        self.completed.add(item.nodeid)
        # print("%s check teardown item:%s fixtures:%s completd:%s" % (
        #    self.wid, item.nodeid, found, self.completed), file=sys.stderr)
        for f in found:
            # print("%s check %s result %s" % (
            #       self.wid, f, self.completed.issuperset(self.fixture_map[f])),
            #       file=sys.stderr)
            # print('%s check result %s %s:%s' % (
            #       self.wid, completed, f, self.fixture_map[f]))
            if self.completed.issuperset(self.fixture_map[f]):
                print(
                    "%s execute test:%s teardown %s" % (self.wid, item.nodeid, f),
                    file=sys.stderr,
                )
                tf.terraform.get_fixture(f).tear_down()
                self.fixture_map.pop(f)

    def pytest_sessionfinish(self, exitstatus):
        if self.wid == "master":
            # print("master session finish", file=sys.stderr)
            return

        completed = {n.strip() for n in self.test_log_reader.readlines()}
        self.completed.update(completed)
        #        print("%s worker session down tracked:%d completed:%d %s" % (
        #            self.wid, len(self.tracked_fixtures),
        #            len(self.completed), completed), file=sys.stderr)
        #        print("%s worker map %s" % (
        #            self.wid, self.fixture_map), file=sys.stderr)

        remains = []
        for f in self.tracked_fixtures:
            if f not in self.fixture_map:
                continue
            if self.completed.issuperset(self.fixture_map[f]):
                print(
                    "%s worker session down cleanup %s" % (self.wid, f), file=sys.stderr
                )
                tf.terraform.get_fixture(f).tear_down()
            else:
                remains.append(str((f, self.fixture_map[f].difference(self.completed))))
        if remains:
            print("%s tf remains %s" % (self.wid, remains), file=sys.stderr)

    # master hooks
    def pytest_report_teststatus(self, report, config):
        # only called from master
        if self.wid != "master" or report.when != "call":
            return
        self.test_log_writer.write(("%s\n" % report.nodeid).encode("utf8"))
        self.test_log_writer.flush()
        os.fsync(self.test_log_writer.fileno())

    def pytest_configure_node(self, node):
        if not node.gateway.spec.popen:
            raise RuntimeError(
                "terraform plugin only compatible with xdist multi-process"
            )
