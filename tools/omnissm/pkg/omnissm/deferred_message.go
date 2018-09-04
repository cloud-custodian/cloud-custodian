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
)

type DeferredActionType int

const (
	InvalidActionType DeferredActionType = iota
	AddTagsToResource
	RequestActivation
	DeregisterInstance
	PutInventory
	PutRegistrationEntry
	DeleteRegistrationEntry
)

type DeferredActionMessage struct {
	Type  DeferredActionType
	Value interface{}
}

func (d *DeferredActionMessage) MarshalJSON() ([]byte, error) {
	data, err := json.Marshal(d.Value)
	if err != nil {
		return nil, errors.Wrap(err, "cannot marshal message value")
	}
	return json.Marshal(struct {
		Type  DeferredActionType
		Value json.RawMessage
	}{
		Type:  d.Type,
		Value: data,
	})
}

func (d *DeferredActionMessage) UnmarshalJSON(data []byte) error {
	var msg struct {
		Type  DeferredActionType
		Value json.RawMessage
	}
	if err := json.Unmarshal(data, &msg); err != nil {
		return errors.Wrap(err, "cannot unmarshal message value")
	}
	*d = DeferredActionMessage{msg.Type, msg.Value}
	return nil
}
