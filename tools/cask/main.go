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
	"os/signal"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"syscall"
	"time"

	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/filters"
	"github.com/docker/docker/client"
	"github.com/docker/docker/pkg/jsonmessage"
	"github.com/docker/docker/pkg/stdcopy"
	"github.com/mattn/go-isatty"
	"github.com/thoas/go-funk"

	image_types "github.com/docker/docker/api/types/image"
)

const containerHome string = "/home/custodian/"
const defaultImageName string = "cloudcustodian/c7n:latest"
const imageOverrideEnv = "CUSTODIAN_IMAGE"
const updateInterval = time.Hour * 12

var version string

func main() {
	// Select image from env or default
	activeImage := getDockerImageName()

	fmt.Printf("Custodian Cask %v (%v)\n", version, activeImage)

	ctx := context.Background()

	// Create a docker client
	dockerClient := getClient()

	// Update docker image if needed
	update(ctx, "docker.io/"+activeImage, dockerClient)

	// Create container
	id := create(ctx, activeImage, dockerClient)

	// Create signal channel and register notify
	handleSignals(ctx, id, dockerClient)

	// Run
	run(ctx, id, dockerClient)
}

// getClient Creates a docker client using the host environment variables
func getClient() *client.Client {
	dockerClient, err := client.NewEnvClient()
	if err != nil {
		log.Fatalf("Unable to create docker client. %v", err)
	}
	return dockerClient
}

// update Pulls the latest docker image and creates
// a marker file so it is not pulled again until
// the specified time elapses or the file is deleted.
func update(ctx context.Context, image string, dockerClient *client.Client) {
	updateMarker := updateMarkerFilename(image)
	now := time.Now()

	// Check if there is a marker indicating last pull for this image
	info, err := os.Stat(updateMarker)

	// If the marker file is not expired
	if err == nil && info.ModTime().Add(updateInterval).After(now) {

		// Query the existing image list for matches
		listFilters := filters.NewArgs()
		listFilters.Add("reference", defaultImageName)

		listOptions := image_types.ListOptions{
			All:     true,
			Filters: listFilters,
		}

		images, err := dockerClient.ImageList(ctx, listOptions)
		if err != nil {
			log.Printf("Failed to enumerate docker images. %v", err)
		}

		// Skip image pull if we have an image already
		if len(images) > 0 {
			return
		}
	}

	// Pull the image

	out, err := dockerClient.ImagePull(ctx, image, image_types.PullOptions{})
	if err != nil {
		log.Printf("Image Pull failed, will use cached image if available. %v", err)
	} else {
		isTerm := isatty.IsTerminal(os.Stdout.Fd())
		_ = jsonmessage.DisplayJSONMessagesStream(out, os.Stdout, 1, isTerm, nil)
	}

	// Touch the marker file
	if _, err := os.Stat(updateMarker); err == nil {
		if err := os.Chtimes(updateMarker, now, now); err != nil {
			log.Printf("Unable to update cache marker file. %v", err)
		}
	} else {
		if _, err = os.OpenFile(updateMarker, os.O_RDWR|os.O_CREATE, 0666); err != nil {
			log.Printf("Unable to write to temporary directory. %v", err)
		}
	}
}

// create a container with appropriate arguments.
// Includes creating mounts and updating paths.
func create(ctx context.Context, image string, dockerClient *client.Client) string {
	// Prepare configuration
	args := os.Args[1:]
	processOutputArgs(&args)
	binds := generateBinds(args)
	envs := generateEnvs()

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
		nil,
		"")
	if err != nil {
		log.Fatal(err)
	}

	return cont.ID
}

// run container and wait for it to complete.
// Copy log output to stdout and stderr.
func run(ctx context.Context, id string, dockerClient *client.Client) {
	// Docker Run
	err := dockerClient.ContainerStart(ctx, id, container.StartOptions{})
	if err != nil {
		log.Fatal(err)
	}

	// Output
	out, err := dockerClient.ContainerLogs(ctx, id, container.LogsOptions{ShowStdout: true, ShowStderr: true, Follow: true})
	if err != nil {
		log.Fatal(err)
	}

	_, err = stdcopy.StdCopy(os.Stdout, os.Stdout, out)
	if err != nil {
		log.Fatal(err)
	}

	err = dockerClient.ContainerRemove(
		ctx, id, container.RemoveOptions{RemoveVolumes: true})
	if err != nil {
		log.Fatal(err)
	}
}

// generateBinds Create the bind mounts for input/output
func generateBinds(args []string) []string {
	var binds []string

	// Loop through all args looking for paths
	// so we can create bind mounts and rewrite the arg
	for i, arg := range args {
		if isPath(arg) {
			containerPath := containerHome + filepath.Base(arg)
			absPath, err := filepath.Abs(arg)
			if err == nil {
				binds = append(binds, absPath+":"+containerHome+filepath.Base(absPath)+":rw")
			}

			args[i] = containerPath
		}

	}

	// Azure CLI support
	azureCliConfig := getAzureCliConfigPath()
	if azureCliConfig != "" {
		// Bind as RW for token refreshes
		binds = append(binds, azureCliConfig+":"+containerHome+".azure:rw")
	}

	// AWS config
	awsConfig := getAwsConfigPath()
	if awsConfig != "" {
		binds = append(binds, awsConfig+":"+containerHome+".aws:ro")
	}

	// Default cache location
	if !funk.Any(funk.Intersect(args, []string{"-f", "--cache"})) {
		cacheDefault := getFolderFromHome(".cache")
		binds = append(binds, cacheDefault+":"+containerHome+".cache:rw")
	}

	return binds
}

func processOutputArgs(argsp *[]string) {
	var outputPath string
	args := *argsp

	for i, arg := range args {
		if strings.HasPrefix(arg, "-s") || strings.HasPrefix(arg, "--output-dir") {
			// normalize argument separator
			if strings.HasPrefix(arg, "-s=") || strings.HasPrefix(arg, "--output-dir=") {
				outputPath = strings.Split(arg, "=")[1]

				args[i] = "-s"
				args = append(args, "")
				copy(args[i+1:], args[i:])
				args[i+1] = outputPath
			}

			// make absolute path and ensure exists
			outputPath, err := filepath.Abs(args[i+1])
			if err != nil {
				log.Fatal(err)
			}

			err = os.MkdirAll(outputPath, 0700)
			if err != nil {
				log.Fatal(err)
			}

			args[i+1] = outputPath
		}
	}

	*argsp = args
}

// generateEnvs Get list of environment variables
func generateEnvs() []string {
	var envs []string

	// Bulk include matching variables
	var re = regexp.MustCompile(`^AWS|^AZURE_|^MSI_|^TENCENTCLOUD_|^GOOGLE|CLOUDSDK`)
	for _, s := range os.Environ() {
		if re.MatchString(s) {
			envs = append(envs, s)
		}
	}

	return envs
}

// getAzureCliConfigPath Find Azure CLI Config if available so
// we can mount it on the container.
func getAzureCliConfigPath() string {
	// Check for override location
	azureCliConfig := os.Getenv("AZURE_CONFIG_DIR")
	if azureCliConfig != "" {
		return filepath.Join(azureCliConfig, "config")
	}

	// Check for default location
	configPath := getFolderFromHome(".azure")

	if _, err := os.Stat(configPath); err == nil {
		return configPath
	}

	return ""
}

// getAwsConfigPath Find AWS Config if available so
// we can mount it on the container.
func getAwsConfigPath() string {
	configPath := getFolderFromHome(".aws")

	if _, err := os.Stat(configPath); err == nil {
		return configPath
	}

	return ""
}

// getFolderFromHome helps us get a
// folder in the users home directory
func getFolderFromHome(subdir string) string {
	var configPath string

	if runtime.GOOS == "windows" {
		configPath = os.Getenv("USERPROFILE")
	} else {
		configPath = os.Getenv("HOME")
	}

	return filepath.Join(configPath, subdir)
}

func isLocalStorage(output string) bool {
	return !(strings.HasPrefix(output, "s3://") ||
		strings.HasPrefix(output, "azure://") ||
		strings.HasPrefix(output, "gs://"))
}

// isPath attempts to confirm if an argument
// is a path, and thus needs a bind
func isPath(arg string) bool {
	_, err := os.Stat(arg)
	if os.IsNotExist(err) {
		return false
	}
	return true
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

	userCacheDir, err := os.UserCacheDir()
	if err != nil {
		log.Fatalf("Unable to get user cache directory. %v", err)
	}

	cacheDir := filepath.Join(userCacheDir, "custodian-cask")

	err = os.Mkdir(cacheDir, 0750)
	if err != nil && !os.IsExist(err) {
		log.Fatalf("Unable to create user cache directory. %v", err)
	}
	return filepath.Join(cacheDir, "cask-update-"+hash[0:5])
}

func handleSignals(ctx context.Context, id string, dockerClient *client.Client) {
	gracefulExit := make(chan os.Signal, 1)
	signal.Notify(gracefulExit, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		sig := <-gracefulExit
		fmt.Printf("Received %v, stopping container\n", sig)
		timeout := 0
		err := dockerClient.ContainerStop(ctx, id, container.StopOptions{Timeout: &timeout})
		if err != nil {
			fmt.Printf("Error stopping container: %v\n", err)
		}
	}()
}
