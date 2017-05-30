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

from common import BaseTest
import yaml

from c7n.resources.s3 import S3EncryptionMissingFilter


class TestS3EncryptionMissingFilter(BaseTest):
    def test_an_encryptionrequired_resource(self):
        f = S3EncryptionMissingFilter({})
        res = f({'Policy': '{"name":"testbucket", "Statement": [{"Sid":"RequiredEncryptedPutObject"}]}'})
        self.assertFalse(res, "testbucket should have been recognized for omission.")

    def test_a_nonencryptionrequired_resource(self):
        f = S3EncryptionMissingFilter({})
        res = f({'Policy': '{"name":"testbucket", "Statement": [{"Sid":"RequiredSomethingUnrelated"}]}'})
        self.assertTrue(res, "testbucket should NOT have been recognized.")

    def test_a_nonencryptionrequired_resource_with_no_policy(self):
        f = S3EncryptionMissingFilter({})
        res = f({'Policy': None})
        self.assertTrue(res, "testbucket should have been recognized as missing the encryption policy.")

    def _get_test_policy(self, name, yaml_doc, record=False):
        if record:
            print "Test is RECORDING"
            session_factory = self.record_flight_data(name)
        else:
            print "Test is replaying"
            session_factory = self.replay_flight_data(name)

        policy = self.load_policy( yaml.load(yaml_doc)['policies'][0], session_factory=session_factory)

        return policy

    def test_against_sandbox(self):
        yml = '''
            policies:
              - name: find-buckets_missing_encryption
                resource: s3
                filters:
                  - s3-encryption-missing
                actions:
                  - type: no-op
        '''
        policy = self._get_test_policy(name="s3encryptionmissingtest", yaml_doc=yml, record=False)
        resources = policy.run()
        from pprint import pprint
        pprint(resources)
        self.assertEqual(len(resources), 10, "10 out of 11 buckets should be returned for not having the requisite"
                         " encryption policy statement.")
