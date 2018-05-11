package main

import (
	"os/exec"

	"github.com/rs/zerolog/log"
)

var (
	// TODO: might need to change
	ssmAgentCmd = mustFindExecutable("amazon-ssm-agent")
	ssmCLICmd   = mustFindExecutable("ssm-cli")
	serviceCmd  = mustFindExecutable("service")
)

func mustFindExecutable(cmdName string) string {
	cmd, err := exec.LookPath(cmdName)
	if err != nil {
		log.Fatal().Msgf("cannot find executable: %#v", cmdName)
	}
	return cmd
}

func restartAgent() error {
	if out, err := exec.Command(serviceCmd, "amazon-ssm-agent", "restart").CombinedOutput(); err != nil {
		log.Debug().Str("combinedOutput", string(out)).Msg("cannot restart SSM agent")
		return err
	}
	return nil
}
