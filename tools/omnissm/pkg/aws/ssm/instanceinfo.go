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

package ssm

import (
	"encoding/json"
	"io/ioutil"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/aws/amazon-ssm-agent/agent/appconfig"
	"github.com/pkg/errors"
)

var (
	// The default path for Agent Registration State on Linux.
	DefaultSSMRegistrationPath = filepath.Join(appconfig.DefaultDataStorePath, "registration")
)

func ReadRegistrationFile(path string) (id string, err error) {
	data, err := ioutil.ReadFile(path)
	if err != nil {
		return
	}
	var s struct {
		ManagedInstanceID string
		Region            string
	}
	err = json.Unmarshal(data, &s)
	if err != nil {
		return
	}
	if strings.HasPrefix(s.ManagedInstanceID, "mi-") {
		return s.ManagedInstanceID, nil
	}
	return
}

// InstanceInfo contains information for instances registered with SSM.  This
// is collected from the output of the following command:
//     ssm-cli get-instance-information
type InstanceInfo struct {
	InstanceId     string `json:"instance-id"`
	Region         string `json:"region"`
	ReleaseVersion string `json:"release-version"`
}

func GetInstanceInformation() (*InstanceInfo, error) {
	cmd, err := exec.LookPath("ssm-cli")
	if err != nil {
		return nil, errors.WithStack(err)
	}
	out, err := exec.Command(cmd, "get-instance-information").Output()
	if err != nil {
		return nil, errors.WithStack(err)
	}
	var info InstanceInfo
	if err := json.Unmarshal(out, &info); err != nil {
		return nil, errors.WithStack(err)
	}
	return &info, nil
}
