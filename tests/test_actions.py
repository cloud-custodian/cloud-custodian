# Copyright 2017 Capital One Services, LLC
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
from botocore.exceptions import ClientError
from c7n.exceptions import PolicyValidationError
from c7n.actions import Action, ActionRegistry
from .common import BaseTest


class ActionTest(BaseTest):

    def test_process_unimplemented(self):
        self.assertRaises(NotImplementedError, Action().process, None)

    def test_filter_resources(self):
        a = Action()
        a.type = 'set-x'
        log_output = self.capture_logging('custodian.actions')
        resources = [
            {'app': 'X', 'state': {'status': 'running'}},
            {'app': 'Y', 'state': {'status': 'stopped'}},
            {'app': 'Z', 'state': {'status': 'running'}}]
        match = a.filter_resources(resources, 'state.status', ('running',))
        assert {'X', 'Z'} == {r['app'] for r in match}
        assert log_output.getvalue().strip() == (
            'set-x implicitly filtered 2 of 3 resources key:state.status on running')

    def test_split_resources_multi_value(self):
        a = Action()
        a.type = 'set-x'
        resources = [
            {'app': 'W'},
            {'app': 'X', 'actions': [{'status': 'ok'}, {'status': 'skip'}]},
            {'app': 'Y', 'actions': [{'status': 'skip'}, {'status': 'ok'}]},
            {'app': 'Z', 'actions': [{'status': 'ok'}, {'status': 'error'}]},
        ]
        match, nomatch = a.split_resources(
            resources, 'actions[].status', exclude=('error',))
        assert {'W', 'X', 'Y'} == {r['app'] for r in match}
        assert {'Z', } == {r['app'] for r in nomatch}

    def test_split_resources_multi_include_exclude(self):
        a = Action()
        a.type = 'set-x'
        resources = [
            {'app': 'W'},
            {'app': 'X', 'actions': [{'status': 'ok'}, {'status': 'skip'}]},
            {'app': 'Y', 'actions': [{'status': 'skip'}, {'status': 'ok'}]},
            {'app': 'Z', 'actions': [{'status': 'ok'}, {'status': 'error'}]},
        ]
        match, nomatch = a.split_resources(
            resources, 'actions[].status', allowed_values=('skip',), exclude=('error',))
        assert {'X', 'Y'} == {r['app'] for r in match}
        assert {'W', 'Z'} == {r['app'] for r in nomatch}

    def test_split_resources_multi_only_no_value(self):
        a = Action()
        a.type = 'set-x'
        resources = [
            {'app': 'W'},
            {'app': 'X', 'actions': [{'status': 'ok'}, {'status': 'skip'}]},
            {'app': 'Y', 'actions': [{'status': 'skip'}, {'status': 'ok'}]},
            {'app': 'Z', 'actions': [{'status': 'ok'}, {'status': 'error'}]},
        ]
        match, nomatch = a.split_resources(
            resources, 'actions[].status', allowed_values=(None,))
        assert {'W'} == {r['app'] for r in match}
        assert {'X', 'Y', 'Z'} == {r['app'] for r in nomatch}

    def test_split_resources_multi_exclude_no_value(self):
        a = Action()
        a.type = 'set-x'
        resources = [
            {'app': 'W'},
            {'app': 'X', 'actions': [{'status': 'ok'}, {'status': 'skip'}]},
            {'app': 'Y', 'actions': [{'status': 'skip'}, {'status': 'ok'}]},
            {'app': 'Z', 'actions': [{'status': 'ok'}, {'status': 'error'}]},
        ]
        match, nomatch = a.split_resources(
            resources, 'actions[].status', exclude=(None,))
        assert {'X', 'Y', 'Z'} == {r['app'] for r in match}
        assert {'W'} == {r['app'] for r in nomatch}

    def test_run_api(self):
        resp = {
            "Error": {"Code": "DryRunOperation", "Message": "would have succeeded"},
            "ResponseMetadata": {"HTTPStatusCode": 412},
        }

        func = lambda: (_ for _ in ()).throw(ClientError(resp, "test"))  # NOQA
        # Hard to test for something because it just logs a message, but make
        # sure that the ClientError gets caught and not re-raised
        Action()._run_api(func)

    def test_run_api_error(self):
        resp = {"Error": {"Code": "Foo", "Message": "Bar"}}
        func = lambda: (_ for _ in ()).throw(ClientError(resp, "test2"))  # NOQA
        self.assertRaises(ClientError, Action()._run_api, func)


class ActionRegistryTest(BaseTest):

    def test_error_bad_action_type(self):
        self.assertRaises(
            PolicyValidationError, ActionRegistry("test.actions").factory, {}, None)

    def test_error_unregistered_action_type(self):
        self.assertRaises(
            PolicyValidationError, ActionRegistry("test.actions").factory, "foo", None
        )
