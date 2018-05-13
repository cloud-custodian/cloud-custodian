/*
Copyright 2018 Capital One Services, LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.

You may obtain a copy of the License at
	http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package client

import (
	"os/exec"

	"github.com/rs/zerolog/log"
)

var (
	SSMAgent = Cmd("amazon-ssm-agent")
	SSMCLI   = Cmd("ssm-cli")
	Service  = Cmd("service")
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
	if out, err := exec.Command(Service.Path(), "amazon-ssm-agent", "restart").CombinedOutput(); err != nil {
		log.Debug().Str("combinedOutput", string(out)).Msg("cannot restart SSM agent")
		return err
	}
	return nil
}
