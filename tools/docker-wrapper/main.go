package main

import (
	"context"
	"fmt"
	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/client"
	"github.com/docker/docker/pkg/stdcopy"
	"io"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
)

const CONTAINER_HOME string = "/home/custodian/"

func main() {
	fmt.Println("Custodian Docker Wrapper")

	cli, err := client.NewEnvClient()
	if err != nil {
		fmt.Println("Unable to create docker client")
		panic(err)
	}

	ctx := context.Background()

	Pull("docker.io/cloudcustodian/c7n:latest", cli, ctx)
	CreateAndRun("cloudcustodian/c7n:latest", cli, ctx)
}

func Pull(image string, cli *client.Client, ctx context.Context) {
	reader, err := cli.ImagePull(ctx, image, types.ImagePullOptions{})
	if err != nil {
		io.Copy(os.Stdout, reader)
		log.Fatal(err)
	}
}

func CreateAndRun(image string, cli *client.Client, ctx context.Context) (string, error) {
	// Prepare configuration
	args := os.Args[1:]
	originalOutput := SubstituteOutput(args)
	originalPolicy := SubstitutePolicy(args)
	binds := GenerateBinds(args, originalOutput, originalPolicy)
	envs := GenerateEnvs()

	// Create container
	cont, err := cli.ContainerCreate(
		ctx,
		&container.Config{
			Image: image,
			Cmd:   args,
			Env: envs,
		},
		&container.HostConfig{
			Binds: binds,
		},
		nil,
		"")
	if err != nil {
		log.Fatal(err)
	}

	// Run container
	err = cli.ContainerStart(ctx, cont.ID, types.ContainerStartOptions{})
	if err != nil {
		log.Fatal(err)
	}

	code, err := cli.ContainerWait(ctx, cont.ID)
	if err != nil {
		log.Fatalf("Status code: %v with error: %v", code, err)
	}

	// Output
	out, err := cli.ContainerLogs(ctx, cont.ID, types.ContainerLogsOptions{ShowStdout: true, ShowStderr: true})
	if err != nil {
		log.Fatal(err)
	}

	stdcopy.StdCopy(os.Stdout, os.Stdout, out)

	return cont.ID, nil
}

func GenerateBinds(args []string, outputPath string, policyPath string) []string {
	// Policy
	policy, err := filepath.Abs(policyPath)
	if err != nil {
		log.Fatalf("Unable to load policy. %v", err)
	}

	containerPolicy := CONTAINER_HOME + filepath.Base(policy)
	binds := []string{
		policy + ":" + containerPolicy + ":ro",
	}

	// Output Path
	if outputPath != "" {
		outputPath, err = filepath.Abs(outputPath)
		if err != nil {
			log.Fatalf("Unable to parse output path. %v", err)
		}

		binds = append(binds, outputPath + ":" + CONTAINER_HOME + "output:rw")
	}

	// Azure CLI support
	azureCliConfig := GetAzureCliConfigPath()
	if azureCliConfig != "" {
		// Bind as RW for token refreshes
		binds = append(binds, azureCliConfig + ":" + CONTAINER_HOME + ".azure:rw")
	}

	return binds
}

func SubstitutePolicy(args []string) string {
	originalPolicy := args[len(args)-1]
	args[len(args)-1] = CONTAINER_HOME+filepath.Base(originalPolicy)

	return originalPolicy
}

func SubstituteOutput(args []string) string {
	var outputPath string

	for i := range args{
		arg := args[i]
		if arg == "-s" || arg == "--output-dir" {
			outputPath = args[i+1]

			if !(strings.HasPrefix(outputPath, "s3://") ||
				strings.HasPrefix(outputPath, "azure://") ||
				strings.HasPrefix(outputPath, "gs://")) {
				args[i+1] = CONTAINER_HOME + "output"
				return outputPath
			}
		}
	}

	return ""
}

func GenerateEnvs() []string {
	var envs []string

	// Bulk include matching variables
	var re = regexp.MustCompile(`^AWS|^AZURE|^GOOGLE`)
	for _, s := range os.Environ() {
		if re.MatchString(s) {
			envs = append(envs, s)
		}
	}

	return envs
}

func GetAzureCliConfigPath() string {
	// Check for override location
	azureCliConfig := os.Getenv("AZURE_CONFIG_DIR")
	if azureCliConfig != "" {
		return filepath.Join(azureCliConfig, "config")
	}

	// Check for default location
	var configPath string

	if runtime.GOOS == "windows" {
		configPath = filepath.Join(os.Getenv("USERPROFILE"), ".azure")
	} else {
		configPath = filepath.Join(os.Getenv("HOME"), ".azure")
	}

	if _, err := os.Stat(configPath); err == nil {
		return configPath
	}

	return ""
}
