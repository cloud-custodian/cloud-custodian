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

package servicectl

import (
	"os/exec"

	"github.com/pkg/errors"
)

type Service interface {
	Start() error
	Stop() error
	Restart() error
}

func run(cmd string, args ...string) ([]byte, error) {
	out, err := exec.Command(cmd, args...).CombinedOutput()
	if err != nil {
		return out, errors.Wrapf(err, "%s command failed", cmd)
	}
	return out, nil
}

func New(name string) (Service, error) {
	// use platform-specific service
	return newService(name)
}
