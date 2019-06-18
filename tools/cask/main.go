// Copyright 2019 Microsoft Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// The package provides a transparent pass-through
// for the Custodian CLI to a Custodian Docker Image
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
const IMAGE_NAME string = "cloudcustodian/c7n:latest"

func main() {
	fmt.Printf("Custodian Cask (%v)\n", IMAGE_NAME)

	ctx := context.Background()

	// Create a docker client
	dockerClient := GetClient()

	// Ensure latest docker image
	Pull("docker.io/" + IMAGE_NAME, dockerClient, ctx)

	// Create container
	id := Create(IMAGE_NAME, dockerClient, ctx)

	// Run
	Run(id, dockerClient, ctx)
}

// Creates a docker client using the host environment variables
func GetClient() *client.Client {
	dockerClient, err := client.NewEnvClient()
	if err != nil {
		log.Fatalf("Unable to create docker client. %v", err)
	}
	return dockerClient
}

// Pulls the latest docker image and warns
// if the image pull fails.  If Docker Hub is offline
// the user can still execute on the local image if available.
func Pull(image string, dockerClient *client.Client, ctx context.Context) {
	out, err := dockerClient.ImagePull(ctx, image, types.ImagePullOptions{ })
	if err != nil {
		log.Printf( "Image Pull failed, will use cached image if available. %v", err)
	}

	io.Copy(os.Stdout, out)
}

// Create a container with appropriate arguments.
// Includes creating mounts and updating paths.
func Create(image string, dockerClient *client.Client, ctx context.Context) string {
	// Prepare configuration
	args := os.Args[1:]
	originalOutput := SubstituteOutput(args)
	originalPolicy := SubstitutePolicy(args)
	binds := GenerateBinds(args, originalOutput, originalPolicy)
	envs := GenerateEnvs()

	// Create container
	cont, err := dockerClient.ContainerCreate(
		ctx,
		&container.Config{
			Image: image,
			Cmd:   args,
			Env: envs,
		},
		&container.HostConfig{
			Binds: binds,
			NetworkMode: "host",
		},
		nil,
		"")
	if err != nil {
		log.Fatal(err)
	}

	return cont.ID
}

// Run container and wait for it to complete.
// Copy log output to stdout and stderr.
func Run(id string, dockerClient *client.Client, ctx context.Context) {
	// Docker Run
	err := dockerClient.ContainerStart(ctx, id, types.ContainerStartOptions{})
	if err != nil {
		log.Fatal(err)
	}

	// Wait
	code, err := dockerClient.ContainerWait(ctx, id)
	if err != nil {
		log.Fatalf("Status code: %v with error: %v", code, err)
	}

	// Output
	out, err := dockerClient.ContainerLogs(ctx, id, types.ContainerLogsOptions{ShowStdout: true, ShowStderr: true})
	if err != nil {
		log.Fatal(err)
	}

	_, err = stdcopy.StdCopy(os.Stdout, os.Stdout, out)
	if err != nil {
		log.Fatal(err)
	}
}

// Create the bind mounts for input/output
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

	// AWS config
	awsConfig := GetAwsConfigPath()
	if awsConfig != "" {
		binds = append(binds, awsConfig + ":" + CONTAINER_HOME + ".aws:ro")
	}

	return binds
}

// Fix the policy arguments
func SubstitutePolicy(args []string) string {
	if strings.EqualFold(args[0], "schema")  ||
		strings.EqualFold(args[0], "version") {
		return ""
	}

	originalPolicy := args[len(args)-1]
	args[len(args)-1] = CONTAINER_HOME+filepath.Base(originalPolicy)

	return originalPolicy
}

// Fix the output arguments
func SubstituteOutput(args []string) string {
	var outputPath string

	for i := range args{
		arg := args[i]
		if arg == "-s" || arg == "--output-dir" {
			outputPath = args[i+1]
				if IsLocalStorage(outputPath) {
					args[i+1] = CONTAINER_HOME + "output"
					return outputPath

				}
		}

		if strings.HasPrefix(arg, "-s=") || strings.HasPrefix(arg, "--output-dir=") {
			outputPath = strings.Split(arg, "=")[1]
			if IsLocalStorage(outputPath) {
				args[i] = "-s=" + CONTAINER_HOME + "output"
				return outputPath
			}
		}
	}

	return ""
}

// Get list of environment variables
func GenerateEnvs() []string {
	var envs []string

	// Bulk include matching variables
	var re = regexp.MustCompile(`^AWS|^AZURE_|^MSI_|^GOOGLE`)
	for _, s := range os.Environ() {
		if re.MatchString(s) {
			envs = append(envs, s)
		}
	}

	return envs
}

// Find Azure CLI Config if available so
// we can mount it on the container.
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

// Find AWS Config if available so
// we can mount it on the container.
func GetAwsConfigPath() string {
	var configPath string

	if runtime.GOOS == "windows" {
		configPath = filepath.Join(os.Getenv("USERPROFILE"), ".aws")
	} else {
		configPath = filepath.Join(os.Getenv("HOME"), ".aws")
	}

	if _, err := os.Stat(configPath); err == nil {
		return configPath
	}

	return ""
}

func IsLocalStorage(output string) bool {
	return !(strings.HasPrefix(output, "s3://") ||
			strings.HasPrefix(output, "azure://") ||
			strings.HasPrefix(output, "gs://"))
}