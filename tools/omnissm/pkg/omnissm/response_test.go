// Copyright 2018 Capital One Services, LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package omnissm_test

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/google/go-cmp/cmp"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ssm"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/omnissm"
)

func TestRegistrationResponseMarshal(t *testing.T) {
	testCases := []struct {
		input    *omnissm.RegistrationResponse
		expected []byte
	}{
		{
			input: &omnissm.RegistrationResponse{
				RegistrationEntry: omnissm.RegistrationEntry{
					Id:            "id",
					CreatedAt:     time.Time{},
					ManagedId:     "managedId",
					AccountId:     "accountId",
					Region:        "region",
					InstanceId:    "instanceId",
					IsTagged:      0, // IsTagged and IsInventoried should be omitted when zero for compatibility
					IsInventoried: 0,
					Activation: ssm.Activation{
						ActivationId:   "aid",
						ActivationCode: "code",
					},
				},
				Region: "us-east-2",
			},
			expected: []byte(`{"id":"id","CreatedAt":"0001-01-01T00:00:00Z","ManagedId":"managedId","AccountId":"accountId","Region":"region","InstanceId":"instanceId","ActivationId":"aid","ActivationCode":"code","region":"us-east-2"}`),
		},
	}

	for i, tc := range testCases {
		data, err := json.Marshal(tc.input)
		if err != nil {
			t.Fatal(err)
		}

		if diff := cmp.Diff(string(data), string(tc.expected)); diff != "" {
			t.Errorf("TestCase %d: after json.Marshal: (-got +want)\n%s", i, diff)
		}
	}
}
