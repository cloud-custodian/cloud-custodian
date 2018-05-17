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

var (
	SSMAgent = Cmd("amazon-ssm-agent")
	SSMCLI   = Cmd("ssm-cli")

	// The Initctl command is used to control upstart jobs
	Initctl = Cmd("initctl")

	// The Systemctl command is used to control systemd services
	Systemctl = Cmd("systemctl")
)

type Cmd string

func (c Cmd) Path() string {
	cmd, err := exec.LookPath(string(c))
	if err != nil {
		log.Fatal().Err(err).Msgf("cannot find executable: %#v", c)
	}
	return cmd
}

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
		// initctl expects commands then job name
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
	if out, err := exec.Command(cmd, "amazon-ssm-agent", "restart").CombinedOutput(); err != nil {
		log.Debug().Str("combinedOutput", string(out)).Msg("cannot restart SSM agent")
		return err
	}
	return nil
}
