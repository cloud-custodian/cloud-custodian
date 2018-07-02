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

package omnissm

import (
	"encoding/json"

	"github.com/pkg/errors"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ec2metadata"
)

type RegistrationRequest struct {
	Provider  string `json:"provider"`
	Document  string `json:"document"`
	Signature string `json:"signature"`
	ManagedId string `json:"managedId,omitempty"`

	document ec2metadata.Document
}

func (r *RegistrationRequest) UnmarshalJSON(data []byte) error {
	type alias RegistrationRequest
	var req alias
	if err := json.Unmarshal(data, &req); err != nil {
		return err
	}
	*r = RegistrationRequest(req)
	return nil
}

func (r *RegistrationRequest) Identity() *ec2metadata.Document {
	return &r.document
}

func (r *RegistrationRequest) Verify() error {
	if err := ec2metadata.Verify([]byte(r.Document), r.Signature); err != nil {
		return err
	}
	if err := json.Unmarshal([]byte(r.Document), &r.document); err != nil {
		return errors.Wrap(err, "cannot unmarshal identity document")
	}
	return nil
}
