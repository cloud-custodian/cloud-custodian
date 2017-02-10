# Copyright 2016 Capital One Services, LLC
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
from c7n.actions import Action, ActionRegistry
from common import BaseTest
from nose.tools import raises


class ActionTest(BaseTest):

    @raises(NotImplementedError)
    def test_process_unimplemented(self):
        action = Action().process(None)
        self.fail('Should have raised NotImplementedError')

    def test_run_api(self):
        resp = {
            'Error': {
                'Code': 'DryRunOperation',
                'Message': 'would have succeeded',
            },
            'ResponseMetadata': {
                'HTTPStatusCode': 412
            }
        }

        func = lambda: (_ for _ in ()).throw(ClientError(resp, 'test'))
        # Hard to test for something because it just logs a message, but make
        # sure that the ClientError gets caught and not re-raised
        Action()._run_api(func)

    @raises(ClientError)
    def test_run_api_error(self):
        resp = {
            'Error': {
                'Code': 'Foo',
                'Message': 'Bar',
            }
        }
        func = lambda: (_ for _ in ()).throw(ClientError(resp, 'test2'))
        Action()._run_api(func)
        self.fail('Should have raised ClientError')


class ActionRegistryTest(BaseTest):
    
    @raises(ValueError)
    def test_error_bad_action_type(self):
        ActionRegistry('test.actions').factory({}, None)
        self.fail('Should have raised ValueError')

    @raises(ValueError)
    def test_error_unregistered_action_type(self):
        ActionRegistry('test.actions').factory('foo', None)
        self.fail('Should have raised ValueError')
