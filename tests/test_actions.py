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
from c7n.actions import Action, ActionRegistry, split_resources_by_results
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

    def test_split_resources_multi_complex_value(self):
        a = Action()
        a.type = 'set-x'
        resources = [
            {'app': 'W'},
            {'app': 'X', 'actions': []},
            {'app': 'Y', 'actions': [{'status': 'skip'}, {'status': 'ok'}]},
            {'app': 'Z', 'actions': [{'status': 'ok'}, {'status': 'error'}]},
        ]
        match, nomatch = a.split_resources(
            resources, 'actions[]', allowed_values=({'status': 'skip'},))
        assert {'Y'} == {r['app'] for r in match}
        assert {'W', 'X', 'Z'} == {r['app'] for r in nomatch}

    def test_split_resources_multi_length(self):
        a = Action()
        a.type = 'set-x'
        resources = [
            {'app': 'W'},
            {'app': 'X', 'actions': []},
            {'app': 'Y', 'actions': [{'status': 'skip'}, {'status': 'ok'}]},
            {'app': 'Z', 'actions': [{'status': 'ok'}, {'status': 'error'}]},
        ]
        match, nomatch = a.split_resources(
            resources, 'length(actions)', allowed_values=(2,))
        assert {'Y', 'Z'} == {r['app'] for r in match}
        assert {'W', 'X'} == {r['app'] for r in nomatch}

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

class ActionResultsTest(BaseTest):

    def test_results_no_id_key(self):
        a = Action()
        a.id_key = None
        resources = [{'id': 'test1'}, {'id': 'test2'}, {'id': 'test3'}]
        a.results.initialize(resources)
        self.assertEqual(a.results.resources, {})

        a.results.ok(resources[0])
        self.assertEqual(resources[0].get(a.results.AnnotationKey), None)

    def test_results_unknown_resource(self):
        """
        Test that setting a result on a resource we don't know about is a no-op
        """
        a = Action()
        a.id_key = 'id'
        original = [{'id': 'test1'}, {'id': 'test2'}, {'id': 'test3'}]
        resources = [{'id': 'test1'}, {'id': 'test2'}, {'id': 'test3'}]
        # a.results.initialize(resources)
        a.results.ok('test1')
        a.results.error('test2', 'badness')
        self.assertEqual(resources, original)

    def test_results_only_once(self):
        """
        Test that setting a result on a resource we don't know about is a no-op
        """
        a = Action()
        a.id_key = 'id'
        resources = [{'id': 'test1'}, {'id': 'test2'}, {'id': 'test3'}]
        a.results.initialize(resources)
        a.results.ok('test1')
        # further results should not get applied
        a.results.error('test1', 'badness')
        # so this should still be in the 'ok' state
        self.assertEqual(resources[0][a.results.AnnotationKey][0]['status'], 'ok')

    def test_results_set_status_by_id(self):
        a = Action()
        a.id_key = 'id'
        resources = [{'id': 'test1'}, {'id': 'test2'}, {'id': 'test3'}]
        a.results.initialize(resources)
        a.results.ok('test1')
        a.results.error('test2', 'badness')
        self.assertEqual(resources[0][a.results.AnnotationKey][0]['status'], 'ok')
        self.assertEqual(resources[1][a.results.AnnotationKey][0]['status'], 'error')

    def test_results_metrics(self):
        a = Action()
        a.id_key = 'id'
        resources = [{'id': 'test1'}, {'id': 'test2'}, {'id': 'test3'}]
        a.results.initialize(resources)
        a.results.ok(resources[0])
        a.results.error(resources[1], "badness")
        a.results.skip(resources[2], "already set")
        a.results.ok("unknown")
        self.assertEqual(a.results.metrics, {"ok": 1, "skip": 1, "error": 1})
        self.assertEqual(a.results.resources, {})

    def test_results_remainder(self):
        a = Action()
        a.id_key = 'id'
        resources = [{'id': 'test1'}, {'id': 'test2'}, {'id': 'test3'}]
        a.results.initialize(resources)
        a.results.ok(resources[0])
        a.results.remaining("error", "something went wrong")
        self.assertEqual(a.results.metrics, {"ok": 1, "skip": 0, "error": 2})
        self.assertEqual(len(resources[0][a.results.AnnotationKey]), 1)
        self.assertEqual(len(resources[1][a.results.AnnotationKey]), 1)
        self.assertEqual(len(resources[2][a.results.AnnotationKey]), 1)
        self.assertEqual(resources[0][a.results.AnnotationKey][0]['status'], 'ok')
        self.assertEqual(resources[1][a.results.AnnotationKey][0]['status'], 'error')
        self.assertEqual(resources[2][a.results.AnnotationKey][0]['status'], 'error')

    def test_results_split_by_results(self):
        resources = [{'id': 'test1'}, {'id': 'test2'}, {'id': 'test3'}]

        a = Action()
        a.id_key = 'id'
        a.results.initialize(resources)
        a.results.ok(resources[0])
        a.results.remaining("skip", "already in correct state")

        self.assertEqual(len(resources[0][a.results.AnnotationKey]), 1)
        self.assertEqual(len(resources[1][a.results.AnnotationKey]), 1)
        self.assertEqual(len(resources[2][a.results.AnnotationKey]), 1)

        a = Action()
        a.id_key = 'id'
        a.results.initialize(resources)
        a.results.error(resources[0], 'invalid action')
        a.results.ok(resources[1])

        self.assertEqual(len(resources[0][a.results.AnnotationKey]), 2)
        self.assertEqual(len(resources[1][a.results.AnnotationKey]), 2)
        self.assertEqual(len(resources[2][a.results.AnnotationKey]), 1)

        ok, err = split_resources_by_results(resources)
        self.assertEqual(len(ok), 2)
        self.assertEqual(len(err), 1)
