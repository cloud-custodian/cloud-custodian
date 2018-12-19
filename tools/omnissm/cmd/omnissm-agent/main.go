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

package main

import (
	"os"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"

	"github.com/capitalone/cloud-custodian/tools/omnissm/cmd/omnissm-agent/inventory"
)

var RootCmd = &cobra.Command{
	Use:              "omnissm-agent",
	Short:            "",
	PersistentPreRun: checkDebug,
}

func checkDebug(cmd *cobra.Command, args []string) {
	if viper.GetBool("verbose") {
		zerolog.SetGlobalLevel(zerolog.DebugLevel)
		log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stderr})
	} else {
		zerolog.SetGlobalLevel(zerolog.InfoLevel)
	}
}

func init() {
	viper.AutomaticEnv()
	viper.SetEnvPrefix("OMNISSM")

	RootCmd.PersistentFlags().CountP("verbose", "v", "increase logging level (debug)")
	viper.BindPFlags(RootCmd.PersistentFlags())
}

func main() {
	RootCmd.AddCommand(RegisterCmd)
	RootCmd.AddCommand(VersionCmd)
	RootCmd.AddCommand(inventory.ProcessCmd)

	if err := RootCmd.Execute(); err != nil {
		log.Fatal().Err(err).Msg("failed to execute RootCmd")
	}
}
