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
	"crypto/sha1"
	"encoding/hex"
	"fmt"
	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/client"
	"github.com/docker/docker/pkg/jsonmessage"
	"github.com/docker/docker/pkg/stdcopy"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"time"
)

const CONTAINER_HOME string = "/home/custodian/"
const DEFAULT_IMAGE_NAME string = "cloudcustodian/c7n:latest"
const IMAGE_OVERRIDE_ENV = "CUSTODIAN_IMAGE"
const UPDATE_INTERVAL = time.Hour

func main() {
	// Select image from env or default
	activeImage := DockerImageName()

	fmt.Printf("Custodian Cask (%v)\n", activeImage)

	ctx := context.Background()

	// Create a docker client
	dockerClient := GetClient()

	// Update docker image if needed
	Update("docker.io/" + activeImage, dockerClient, ctx)

	// Create container
	id := Create(activeImage, dockerClient, ctx)

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

// Pulls the latest docker image and creates
// a marker file so it is not pulled again until
// the specified time elapses or the file is deleted.
func Update(image string, dockerClient *client.Client, ctx context.Context) {
	updateMarker := UpdateMarkerFilename(image)
	now := time.Now()

	// Check if there is a marker indicating last pull for this image
	info, err := os.Stat(updateMarker)
	if err == nil && info.ModTime().Add(UPDATE_INTERVAL).After(now) {
		fmt.Printf("Skipped image pull - Last checked %d minutes ago.\n\n", uint(now.Sub(info.ModTime()).Minutes()))
		return
	}

	// Pull the image
	out, err := dockerClient.ImagePull(ctx, image, types.ImagePullOptions{ })
	if err != nil {
		log.Printf( "Image Pull failed, will use cached image if available. %v", err)
	}

	_ = jsonmessage.DisplayJSONMessagesStream(out, os.Stdout, 1, true, nil)

	// Update the marker file
	_, err = os.OpenFile(updateMarker, os.O_RDONLY|os.O_CREATE, 0666)
	if err != nil {
		log.Printf( "Unable to write to temporary directory. %v", err)
	}
}

// Create a container with appropriate arguments.
// Includes creating mounts and updating paths.
func Create(image string, dockerClient *client.Client, ctx context.Context) string {
	// Prepare configuration
	args := os.Args[1:]
	originalOutput := SubstituteOutput(args)
	originalPolicy := SubstitutePolicy(args)
	binds := GenerateBinds(originalOutput, originalPolicy)
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

	// Output
	out, err := dockerClient.ContainerLogs(ctx, id, types.ContainerLogsOptions{ShowStdout: true, ShowStderr: true, Follow: true})
	if err != nil {
		log.Fatal(err)
	}

	_, err = stdcopy.StdCopy(os.Stdout, os.Stdout, out)
	if err != nil {
		log.Fatal(err)
	}
}

// Create the bind mounts for input/output
func GenerateBinds(outputPath string, policyPath string) []string {
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
	if len(args) == 0 ||
		strings.EqualFold(args[0], "schema")  ||
		strings.EqualFold(args[0], "version") {
		return ""
	}

	originalPolicy := args[len(args)-1]
	args[len(args)-1] = CONTAINER_HOME + filepath.Base(originalPolicy)

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

func DockerImageName() string {
	image := os.Getenv(IMAGE_OVERRIDE_ENV)
	if len(image) == 0 {
		return DEFAULT_IMAGE_NAME
	}
	return image
}

func UpdateMarkerFilename(image string) string {
	sha := sha1.New()
	sha.Write([]byte(image))
	hash := hex.EncodeToString(sha.Sum(nil))
	return filepath.Join(os.TempDir(), "custodian-cask-update-" + hash[0:5])
}