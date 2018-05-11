package main

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
