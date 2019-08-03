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
	"log"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/client"
	"github.com/docker/docker/pkg/jsonmessage"
	"github.com/docker/docker/pkg/stdcopy"
)

const containerHome string = "/home/custodian/"
const defaultImageName string = "cloudcustodian/c7n:latest"
const imageOverrideEnv = "CUSTODIAN_IMAGE"
const updateInterval = time.Hour

func main() {
	// Select image from env or default
	activeImage := getDockerImageName()

	fmt.Printf("Custodian Cask (%v)\n", activeImage)

	ctx := context.Background()

	// Create a docker client
	dockerClient := GetClient()

	// Update docker image if needed
	Update(ctx, "docker.io/"+activeImage, dockerClient)

	// Create container
	id := Create(ctx, activeImage, dockerClient)

	// Run
	Run(ctx, id, dockerClient)
}

// GetClient Creates a docker client using the host environment variables
func GetClient() *client.Client {
	dockerClient, err := client.NewEnvClient()
	if err != nil {
		log.Fatalf("Unable to create docker client. %v", err)
	}
	return dockerClient
}

// Update Pulls the latest docker image and creates
// a marker file so it is not pulled again until
// the specified time elapses or the file is deleted.
func Update(ctx context.Context, image string, dockerClient *client.Client) {
	updateMarker := updateMarkerFilename(image)
	now := time.Now()

	// Check if there is a marker indicating last pull for this image
	info, err := os.Stat(updateMarker)
	if err == nil && info.ModTime().Add(updateInterval).After(now) {
		fmt.Printf("Skipped image pull - Last checked %d minutes ago.\n\n", uint(now.Sub(info.ModTime()).Minutes()))
		return
	}

	// Pull the image
	out, err := dockerClient.ImagePull(ctx, image, types.ImagePullOptions{})
	if err != nil {
		log.Printf("Image Pull failed, will use cached image if available. %v", err)
	} else {
		_ = jsonmessage.DisplayJSONMessagesStream(out, os.Stdout, 1, true, nil)
	}

	// Update the marker file
	_, err = os.OpenFile(updateMarker, os.O_RDONLY|os.O_CREATE, 0666)
	if err != nil {
		log.Printf("Unable to write to temporary directory. %v", err)
	}
}

// Create a container with appropriate arguments.
// Includes creating mounts and updating paths.
func Create(ctx context.Context, image string, dockerClient *client.Client) string {
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
			Env:   envs,
		},
		&container.HostConfig{
			Binds:       binds,
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
func Run(ctx context.Context, id string, dockerClient *client.Client) {
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

	err = dockerClient.ContainerRemove(
		ctx, id, types.ContainerRemoveOptions{RemoveVolumes: true})
	if err != nil {
		log.Fatal(err)
	}
}

// GenerateBinds Create the bind mounts for input/output
func GenerateBinds(outputPath string, policyPath string) []string {
	// Policy
	policy, err := filepath.Abs(policyPath)
	if err != nil {
		log.Fatalf("Unable to load policy. %v", err)
	}

	containerPolicy := containerHome + filepath.Base(policy)
	binds := []string{
		policy + ":" + containerPolicy + ":ro",
	}

	// Output Path
	if outputPath != "" {
		outputPath, err = filepath.Abs(outputPath)
		if err != nil {
			log.Fatalf("Unable to parse output path. %v", err)
		}

		binds = append(binds, outputPath+":"+containerHome+"output:rw")
	}

	// Azure CLI support
	azureCliConfig := GetAzureCliConfigPath()
	if azureCliConfig != "" {
		// Bind as RW for token refreshes
		binds = append(binds, azureCliConfig+":"+containerHome+".azure:rw")
	}

	// AWS config
	awsConfig := GetAwsConfigPath()
	if awsConfig != "" {
		binds = append(binds, awsConfig+":"+containerHome+".aws:ro")
	}

	return binds
}

// SubstitutePolicy Fix the policy arguments
func SubstitutePolicy(args []string) string {
	if len(args) == 0 ||
		strings.EqualFold(args[0], "schema") ||
		strings.EqualFold(args[0], "version") {
		return ""
	}

	originalPolicy := args[len(args)-1]
	args[len(args)-1] = containerHome + filepath.Base(originalPolicy)

	return originalPolicy
}

// SubstituteOutput Fix the output arguments
func SubstituteOutput(args []string) string {
	var outputPath string

	for i := range args {
		arg := args[i]
		if arg == "-s" || arg == "--output-dir" {
			outputPath = args[i+1]
			if isLocalStorage(outputPath) {
				args[i+1] = containerHome + "output"
				return outputPath

			}
		}

		if strings.HasPrefix(arg, "-s=") || strings.HasPrefix(arg, "--output-dir=") {
			outputPath = strings.Split(arg, "=")[1]
			if isLocalStorage(outputPath) {
				args[i] = "-s=" + containerHome + "output"
				return outputPath
			}
		}
	}

	return ""
}

// GenerateEnvs Get list of environment variables
func GenerateEnvs() []string {
	var envs []string

	// Bulk include matching variables
	var re = regexp.MustCompile(`^AWS|^AZURE_|^MSI_|^GOOGLE|CLOUDSDK`)
	for _, s := range os.Environ() {
		if re.MatchString(s) {
			envs = append(envs, s)
		}
	}

	return envs
}

// GetAzureCliConfigPath Find Azure CLI Config if available so
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

// GetAwsConfigPath Find AWS Config if available so
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

func isLocalStorage(output string) bool {
	return !(strings.HasPrefix(output, "s3://") ||
		strings.HasPrefix(output, "azure://") ||
		strings.HasPrefix(output, "gs://"))
}

func getDockerImageName() string {
	image := os.Getenv(imageOverrideEnv)
	if len(image) == 0 {
		return defaultImageName
	}
	return image
}

func updateMarkerFilename(image string) string {
	sha := sha1.New()
	sha.Write([]byte(image))
	hash := hex.EncodeToString(sha.Sum(nil))
	return filepath.Join(os.TempDir(), "custodian-cask-update-"+hash[0:5])
}
