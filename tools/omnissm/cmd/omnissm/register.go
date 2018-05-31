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
	"github.com/rs/zerolog/log"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/identity"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/manager/client"
)

var RegisterCmd = &cobra.Command{
	Use:   "register",
	Short: "",
	Run: func(cmd *cobra.Command, args []string) {
		url := viper.GetString("register_endpoint")
		if url == "" {
			endpoints := viper.GetStringMapString("register_endpoints")
			if endpoints != nil {
				region := identity.GetLocalInstanceRegion()
				if region == "" {
					log.Fatal().Msg("unable to determine instance region from metadata")
				}
				url = endpoints[region]
			}
		}
		if url == "" {
			log.Fatal().Msg("registration url (OMNISSM_REGISTER_ENDPOINT) cannot be blank")
		}
		c, err := client.New(&client.Config{
			Document:        string(identity.GetLocalInstanceDocument()),
			Signature:       string(identity.GetLocalInstanceSignature()),
			RegistrationURL: url,
		})
		if err != nil {
			log.Fatal().Msgf("unable to initialize node: %v", err)
		}
		if c.ManagedId() != "" {
			log.Info().Str("managedId", c.ManagedId()).Msg("instance already registered")
			return
		}
		log.Info().Msg("attempting to register instance ...")
		if err := c.Register(); err != nil {
			log.Fatal().Msgf("Error registering node %v", err)
		}
		if err := c.Update(); err != nil {
			log.Fatal().Msgf("Error recording node ssm id %v", err)
		}
		log.Info().Str("managedId", c.ManagedId()).Msg("instance registered")
	},
}

func init() {
	RegisterCmd.Flags().String("register-endpoint", "", "")
	viper.BindPFlags(RegisterCmd.Flags())
}
