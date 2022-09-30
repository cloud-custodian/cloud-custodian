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

import json
import os
import subprocess
import sys
from collections import UserString, defaultdict
from typing import Any, Dict, Optional, Tuple, Union

import jmespath
import pytest
from py.path import local

from .exceptions import InvalidState, ModuleNotFound, TerraformCommandFailed
from .options import teardown as td


class TerraformRunner(object):

    command_templates = {
        "init": "init {input} {color} {plugin_dir}",
        "apply": "apply {input} {color} {state} {approve} {plan}",
        "plan": "plan {input} {color} {state} {output}",
        "destroy": "destroy {input} {color} {state} {approve}",
        "show": "show {color} -json {state_path}",
    }

    template_defaults = {
        "input": "-input=false",
        "color": "-no-color",
        "approve": "-auto-approve",
    }

    debug = False

    def __init__(
        self,
        work_dir,
        state_path=None,
        module_dir=None,
        plugin_cache=None,
        stream_output=None,
        tf_bin=None,
    ):

        self.work_dir = work_dir
        self.module_dir = module_dir
        # use parent dir of work/data dir to avoid
        # https://github.com/hashicorp/terraform/issues/22999
        self.state_path = state_path or os.path.join(work_dir, "..", "terraform.tfstate")
        self.stream_output = stream_output
        self.plugin_cache = plugin_cache or ""
        self.tf_bin = tf_bin

    def apply(self, plan=True):
        """run terraform apply"""
        if plan is True:
            plan_path = os.path.join(self.work_dir, "tfplan")
            self.plan(plan_path)
            apply_args = self._get_cmd_args("apply", plan=plan_path)
        elif plan:
            apply_args = self._get_cmd_args("apply", plan="")
        self._run_cmd(apply_args)
        return TerraformState.from_file(self.state_path, self)

    def plan(self, output=""):
        output = output and "-out=%s" % output or ""
        self._run_cmd(self._get_cmd_args("plan", output=output))

    def init(self):
        self._run_cmd(self._get_cmd_args("init", plugin_dir=""))

    def destroy(self):
        self._run_cmd(self._get_cmd_args("destroy"))

    def show(self):
        return json.loads(
            self._run_cmd(
                self._get_cmd_args("show", state_path=self.state_path), output=True
            ).decode("utf8")
        )

    def _get_cmd_args(self, cmd_name, tf_bin=None, env=None, **kw):
        tf_bin = tf_bin and tf_bin or self.tf_bin
        kw.update(self.template_defaults)
        kw["state"] = self.state_path and "-state=%s" % self.state_path or ""
        return [tf_bin] + list(
            filter(None, self.command_templates[cmd_name].format(**kw).split(" "))
        )

    def _run_cmd(self, args, output=False):
        env = dict(os.environ)
        tf_env = {}
        if LazyPluginCacheDir.resolve():
            tf_env["TF_PLUGIN_CACHE_DIR"] = LazyPluginCacheDir.resolve()
        tf_env["TF_IN_AUTOMATION"] = "yes"
        if self.module_dir:
            tf_env["TF_DATA_DIR"] = self.work_dir
        cwd = self.module_dir or self.work_dir
        env.update(tf_env)
        print("run cmd", args, tf_env, cwd, file=sys.stderr)
        run_cmd = subprocess.check_call
        if output:
            run_cmd = subprocess.check_output
        return run_cmd(args, cwd=cwd, stderr=subprocess.STDOUT, env=env)


class TerraformStateJson(UserString):
    @classmethod
    def from_dict(cls, state: Dict[str, Any]):
        """create TerraformStateJson from dictionary"""
        s = cls("")
        s.update_dict(state)
        return s

    def update(self, state: str):
        """update TerraformStateJson object with new data"""
        if not isinstance(state, str):
            raise ValueError(f"{state} is not a string")

        self.data = str(state)

    def update_dict(self, state: Dict[str, Any]):
        """update TerraformStateJson from a dict"""
        self.update(json.dumps(state, indent=4))

    @property
    def dict(self):
        """return the TerraformStateJson as a dict"""
        return json.loads(self.data)

    @dict.setter
    def dict(self, data: Dict[str, Any]):
        """update TerraformStateJson from a dict"""
        try:
            self.update_dict(data)
        except (ValueError, TypeError):
            raise ValueError("Not a serializable object")


class TerraformState(object):
    """Abstraction over a terrafrom state file with helpers.

    resources dict contains a minimal representation of a terraform
    state file with enough identity information to query a resource
    from the api.

    resources dict is a nested data structure corresponding to
       resource_type -> resource name -> resource attributes.

    by default all resources will have an 'id' attribute, additional
    attributes which contain the key 'name' will also be present.
    """

    def __init__(self, resources, outputs, runner=None):
        self._runner = runner
        self.outputs = outputs
        self.resources = resources

    @property
    def work_dir(self):
        if self._runner:
            return self._runner.work_dir

    @property
    def terraform(self):
        if self._runner:
            return self._runner

    def __getitem__(self, k):
        v = self.get(k)
        if v is None:
            raise KeyError(k)
        return v

    def get(self, k, default=None):
        """accessor to resource attributes.

        supports a few shortcuts for ease of use.

        key can be a jmespath expression in which case the evaluation
        is returned.

        if key is a unique resource name, then its data is returned, if
        the data is a singleton key dictionary with 'id', then just then
        the string value of 'id' is returned.
        """
        if "." in k:
            return jmespath.search(k, self.resources)
        found = False
        for rtype in self.resources:
            for rname in self.resources[rtype]:
                if rname == k:
                    assert found is False, "Ambigious resource name %s" % k
                    found = self.resources[rtype][rname]
        if found:
            if len(found) == 1:
                return found["id"]
            return found
        return default

    @classmethod
    def from_file(cls, path: str, runner=None):
        """create TerraformState from a file

        File can either be a Terraform Plan state, or a recorded
        pytest-terraform state
        """
        if not os.path.isfile(path):
            raise InvalidState("{} could not be located".format(path))

        with open(path) as fh:
            state = fh.read()

        return cls.from_string(state, runner)

    @classmethod
    def from_string(cls, state: Union[TerraformStateJson, str], runner=None):
        """create TerraformState from string

        State string can be a bytestring or a TerraformStateJson
        string object
        """
        resources, outputs = cls.parse_state(state)
        return cls(resources, outputs, runner)

    def update(self, state: Union[TerraformStateJson, str]):
        """update TerraformState values"""
        resources, outputs = self.parse_state(state)
        self.resources = resources
        self.outputs = outputs

    @staticmethod
    def parse_state(
        state: Union[TerraformStateJson, str]
    ) -> Tuple[Dict[str, any], Dict[str, Any]]:
        """extract resources and outputs from state

        where state is one of the following:
        * Terraform state output as a string
        * Recorded pytest-terraform state
        * TerraformStateJson object
        """
        if isinstance(state, TerraformStateJson):
            data = state.dict
        else:
            data = json.loads(state)

        if "pytest-terraform" in data:
            return (data["resources"], data["outputs"])

        resources = {}
        outputs = {}

        for r in data.get("resources", ()):
            rmap = resources.setdefault(r["type"], {})
            rmap[r["name"]] = dict(r["instances"][0]["attributes"])

        outputs = data.get("outputs", {})
        for m in data.get("modules", ()):
            for k, r in m.get("resources", {}).items():
                if k.startswith("data"):
                    continue
                module, rname = k.split(".", 1)
                rmap = resources.setdefault(module, {})
                rattrs = {"id": r["primary"]["id"]}
                for kattr, vattr in r["primary"]["attributes"].items():
                    if "name" in kattr and vattr != rattrs["id"]:
                        rattrs[kattr] = vattr
                rmap[rname] = rattrs

        return (resources, outputs)

    def export(self):
        """export state as a TerraformStateJson UserString"""

        state = {
            "pytest-terraform": 1,
            "outputs": self.outputs,
            "resources": self.resources,
        }

        return TerraformStateJson.from_dict(state)

    def save(self, state_path: Optional[str] = None) -> Optional[TerraformStateJson]:
        """export state to a file"""

        output = self.export()
        if not state_path:
            return output

        with open(state_path, "w") as fh:
            fh.write(str(output))


class TerraformTestApi(TerraformState):
    """public api to tests as fixture value."""


class PlaceHolderValue(object):
    """Lazy / Late resolved named values.

    many of our instantiations are at module import time, to support
    runtime configuration from cli/ini options we utilize a lazy
    loaded value set which is configured for final values via hooks
    (early, post conf, pre collection).
    """

    def __init__(self, name):
        self.name = name
        self.value = None

    def resolve(self, default=None):
        if not self.value and default:
            raise ValueError("PlaceHolderValue %s not resolved" % self.name)
        return self.value or default


LazyReplay = PlaceHolderValue("tf_replay")
LazyModuleDir = PlaceHolderValue("module_dir")
LazyPluginCacheDir = PlaceHolderValue("plugin_cache")
LazyTfBin = PlaceHolderValue("tf_bin_path")
PytestConfig = PlaceHolderValue("pytestconfig")


class TerraformFixture(object):
    def __init__(
        self,
        tf_bin,
        plugin_cache,
        scope,
        tf_root_module,
        test_dir,
        replay,
        teardown,
        pytest_config,
    ):
        self.tf_bin = tf_bin
        self.tf_root_module = tf_root_module
        self.test_dir = test_dir
        self.scope = scope
        self.replay = replay
        self.runner = None
        self.teardown_config = td.resolve(teardown)
        self.config = pytest_config

    @property
    def name(self):
        return "%s" % self.tf_root_module

    __name__ = name

    def resolve_module_dir(self):
        candidates = [
            self.test_dir.join(self.tf_root_module),
            self.test_dir.join("terraform", self.tf_root_module),
            self.test_dir.dirpath().join(self.tf_root_module),
            self.test_dir.dirpath().join("terraform", self.tf_root_module),
        ]
        if LazyModuleDir.resolve():
            candidates.insert(0, local(LazyModuleDir.resolve()).join(self.tf_root_module))
        for candidate in candidates:
            if not candidate.check(exists=1, dir=1):
                continue
            return candidate
        raise ModuleNotFound(self.tf_root_module)

    def get_runner(self, module_dir, work_dir):
        return TerraformRunner(
            str(work_dir),
            module_dir=module_dir,
            plugin_cache=LazyPluginCacheDir.resolve(),
            tf_bin=LazyTfBin.resolve(),
        )

    def __call__(self, request, tmpdir_factory, worker_id):
        module_dir = self.resolve_module_dir()
        if self.replay:
            replay_resources = os.path.join(module_dir, "tf_resources.json")
            if not os.path.exists(replay_resources):
                raise ValueError(
                    "Replay resources don't exist for %s" % self.tf_root_module
                )
            return TerraformTestApi.from_file(
                os.path.join(module_dir, "tf_resources.json")
            )
        work_dir = tmpdir_factory.mktemp(self.tf_root_module, numbered=True).join("work")
        self.runner = self.get_runner(module_dir, work_dir)
        return self.create(request, module_dir)

    def create(self, request, module_dir):
        print("tf create %s" % self.tf_root_module, file=sys.stderr)
        self.runner.init()
        if self.teardown_config != td.OFF:
            request.addfinalizer(self.tear_down)
        try:
            state = self.runner.apply()
            state_json = state.export()
            test_api = TerraformTestApi.from_string(state_json, self.runner)

            self.config.hook.pytest_terraform_modify_state(tfstate=state_json)

            state.update(state_json)
            state.save(module_dir.join("tf_resources.json"))

            return test_api
        except Exception:
            raise

    def tear_down(self):
        # config behavor on runner
        print("tf teardown %s" % self.tf_root_module, file=sys.stderr)
        try:
            self.runner.destroy()
        except subprocess.CalledProcessError as e:
            if self.teardown_config == td.IGNORE:
                return
            raise TerraformCommandFailed from e


class FixtureDecoratorFactory(object):
    """Generate fixture decorators on the fly."""

    scope_class_map = defaultdict(lambda: TerraformFixture)

    # Make accessing teardown options easier for users
    TEARDOWN_IGNORE = td.IGNORE
    TEARDOWN_OFF = td.OFF
    TEARDOWN_ON = td.ON

    def __init__(self):
        self._fixtures = []

    def get_fixtures(self):
        return list(self._fixtures)

    def get_fixture(self, name):
        for f in self._fixtures:
            if f.name == name:
                return f
        raise KeyError(name)

    def __call__(
        self,
        terraform_dir,
        scope="function",
        replay=None,
        name=None,
        teardown=td.DEFAULT,
    ):
        # We have to hook into where fixture discovery will find
        # our fixtures, the easiest option is to store on the module that
        # originated the call, all test modules get scanned for
        # fixtures. The alternative is to try and keep a set and
        # store. this particular setup is to support decorator usage.
        # ie. its gross on one hand and very pratical for consumers
        # on the other.
        f = sys._getframe(1)
        name = name or terraform_dir
        test_dir = local(_frame_path(f)).dirpath()
        if replay is None:
            replay = LazyReplay.resolve()
        found = None
        for tf in self._fixtures:
            if tf.tf_root_module == terraform_dir:
                assert scope == tf.scope, (
                    "Same tf module:%s used at different scopes"
                ) % (terraform_dir)
                found = tf
        if found:
            return self.nonce_decorator
        tclass = self.scope_class_map[scope]
        tfix = tclass(
            LazyTfBin,
            LazyPluginCacheDir,
            scope,
            terraform_dir,
            test_dir,
            replay,
            teardown,
            PytestConfig.resolve(),
        )
        self._fixtures.append(tfix)
        marker = pytest.fixture(scope=scope, name=name)
        f.f_locals[name] = marker(tfix)
        return self.nonce_decorator

    @staticmethod
    def nonce_decorator(func):
        pytest.mark.terraform(func)
        return func


def _frame_path(f):
    start = f
    while f:
        if "__file__" in f.f_locals:
            return f.f_locals["__file__"]
        f = f.f_back
    raise RuntimeError("frame path not found %s" % start)


terraform = FixtureDecoratorFactory()
