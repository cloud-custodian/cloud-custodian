package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"os"
	"time"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var RootCmd = &cobra.Command{
	Use:              "omnissm",
	Short:            "",
	PersistentPreRun: checkDebug,
}

var ProcessCmd = &cobra.Command{
	Use:   "ps",
	Short: "",
	Run: func(cmd *cobra.Command, args []string) {
		info, err := getInstanceInformation()
		if err != nil {
			log.Fatal().Err(err).Msg("cannot get instance information")
		}
		logger := log.With().Str("managedId", info.InstanceId).Logger()
		processes, err := ListAllProcesses()
		if err != nil {
			log.Fatal().Err(err).Msg("cannot list processes")
		}
		inventory := map[string]interface{}{
			"SchemaVersion": "1.0",
			"TypeName":      "Custom:ProcessInfo",
			"CaptureTime":   time.Now().UTC().Format("2006-01-02T15:04:05Z"),
			"Content":       processes,
		}
		data, err := json.MarshalIndent(inventory, "", "   ")
		if err != nil {
			logger.Fatal().Err(err).Msg("cannot marshal inventory")
		}
		path := fmt.Sprintf("/var/lib/amazon/ssm/%s/inventory/custom/ProcessInfo.json", info.InstanceId)
		if err := ioutil.WriteFile(path, data, 0644); err != nil {
			logger.Fatal().Err(err).Msgf("cannot write file: %#v", path)
		}
		logger.Info().Msg("process inventory completed successfully")
	},
}

var RegisterCmd = &cobra.Command{
	Use:   "register",
	Short: "",
	Run: func(cmd *cobra.Command, args []string) {
		u := viper.GetString("register_endpoint")
		if u == "" {
			log.Fatal().Msg("registration url (OMNISSM_REGISTER_ENDPOINT) cannot be blank")
		}
		n, err := NewNode(&Config{
			Identity:        *getLocalInstanceIdentity(),
			RegistrationURL: u,
		})
		if err != nil {
			log.Fatal().Msgf("unable to initialize node: %v", err)
		}
		if n.managedId != "" {
			log.Fatal().Str("managedId", n.managedId).Msg("instance already registered")
		}
		log.Info().Msg("attempting to register instance ...")
		if err := n.Register(); err != nil {
			log.Fatal().Msgf("Error registering node %v", err)
		}
		if err := n.Update(); err != nil {
			log.Fatal().Msgf("Error recording node ssm id %v", err)
		}
		log.Info().Str("managedId", n.managedId).Msg("instance registered")
	},
}

var VersionCmd = &cobra.Command{
	Use:   "version",
	Short: "",
	Run: func(cmd *cobra.Command, args []string) {
		info, err := getInstanceInformation()
		if err != nil {
			log.Fatal().Err(err).Msgf("cannot get instance info")
		}
		fmt.Println(info.ReleaseVersion)
	},
}

func checkDebug(cmd *cobra.Command, args []string) {
	if viper.GetBool("verbose") {
		zerolog.SetGlobalLevel(zerolog.DebugLevel)
		log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stderr})
	}
}

func init() {
	viper.AutomaticEnv()
	viper.SetEnvPrefix("OMNISSM")

	RootCmd.PersistentFlags().CountP("verbose", "v", "increase logging level (debug)")
	viper.BindPFlags(RootCmd.PersistentFlags())

	RegisterCmd.Flags().String("register-endpoint", "", "")
	viper.BindPFlags(RegisterCmd.Flags())
}

func main() {
	RootCmd.AddCommand(ProcessCmd, RegisterCmd, VersionCmd)
	if err := RootCmd.Execute(); err != nil {
		log.Fatal().Err(err).Msg("failed to execute RootCmd")
	}
}
