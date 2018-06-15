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

package client

import (
	"os/exec"

	"github.com/pkg/errors"
	"github.com/rs/zerolog/log"
)

func restartAgent() error {
	cmd, err := exec.LookPath("systemctl")
	if err != nil {
		if execErr, ok := err.(*exec.Error); !ok && execErr.Err != exec.ErrNotFound {
			return errors.Wrap(err, "unable to find systemctl")
		}
	}
	if cmd == "" {
		var err error
		cmd, err = exec.LookPath("initctl")
		if err != nil {
			return errors.New("cannot find systemctl or initctl")
		}
		// to better ensure that it restarts successfully stop and start are
		// called rather than relying on proper implementation of restart
		if out, err := exec.Command(cmd, "stop", "amazon-ssm-agent").CombinedOutput(); err != nil {
			log.Debug().Err(err).Str("combinedOutput", string(out)).Msg("cannot restart SSM agent")
		}
		if out, err := exec.Command(cmd, "start", "amazon-ssm-agent").CombinedOutput(); err != nil {
			log.Debug().Str("combinedOutput", string(out)).Msg("cannot restart SSM agent")
			return err
		}
		return nil
	}
	if out, err := exec.Command(cmd, "restart", "amazon-ssm-agent").CombinedOutput(); err != nil {
		log.Debug().Str("combinedOutput", string(out)).Msg("cannot restart SSM agent")
		return err
	}
	return nil
}
