/*
Copyright 2018 Capital One Services, LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.

You may obtain a copy of the License at
	http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"
)

// SSMAgentRegistration Sourced from /var/lib/amazon/ssm/registration
type SSMAgentRegistration struct {
	ManagedInstanceID string
	Region            string
}

// LinuxSSMRegistrationPath Linux Path to Agent Registration State
const LinuxSSMRegistrationPath = "/var/lib/amazon/ssm/registration"

// IdentityURL ec2 metadata server instance identity document
const IdentityURL = "http://169.254.169.254/latest/dynamic/instance-identity/document"

// SignatureURL RSA SHA256 Signature of identity document
const SignatureURL = "http://169.254.169.254/latest/dynamic/instance-identity/signature"

// FetchContents Retrieve contents of URL
func FetchContents(uri string) ([]byte, error) {
	response, err := http.Get(uri)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	body, err := ioutil.ReadAll(response.Body)
	if err != nil {
		return nil, err
	}
	return body, nil
}

func main() {
	// If no ssm-agent installation, exit
	ssmCmdPath, err := exec.LookPath("amazon-ssm-agent")
	if err != nil {
		fmt.Println("Could not find amazon-ssm-agent binary")
		return
	}
	// If we have a current registration for hybrid mode, exit
	agentRaw, err := ioutil.ReadFile(LinuxSSMRegistrationPath)
	if err == nil {
		agentReg := SSMAgentRegistration{}
		err = json.Unmarshal(agentRaw, &agentReg)
		if err == nil {
			if strings.HasPrefix(agentReg.ManagedInstanceID, "mi-") {
				fmt.Println("SSM Agent registered already", agentReg.ManagedInstanceID)
				return
			}
			fmt.Println("SSM Agent overriding registration", agentReg.ManagedInstanceID)
		}
	}

	identity, err := FetchContents(IdentityURL)
	if err != nil {
		panic(err)
	}
	signature, err := FetchContents(SignatureURL)
	if err != nil {
		panic(err)
	}

	regBody := map[string]string{
		"provider":  "aws",
		"identity":  string(identity),
		"signature": string(signature),
	}

	regSerial, err := json.Marshal(regBody)
	if err != nil {
		panic(err)
	}

	var netClient = &http.Client{
		Timeout: time.Second * 10,
	}

	registrationURL := os.Getenv("OMNISSM_URI")
	if len(registrationURL) < 1 {
		fmt.Println("Missing Registration Endpoint Env Var (OMNISSM_URI)")
		return
	}
	fmt.Println("Registration Request", string(regSerial))

	response, err := netClient.Post(
		registrationURL, "application/json", bytes.NewReader(regSerial))

	regResultBody, err := ioutil.ReadAll(response.Body)
	if err != nil {
		panic(err)
	}

	if response.StatusCode != 200 {
		fmt.Println("Registration Error", string(regResultBody))
		return
	}

	regResult := map[string]string{}

	fmt.Println("Registration Result", string(regResultBody))
	err = json.Unmarshal(regResultBody, &regResult)
	if err != nil {
		panic(err)
	}
	errCode, ok := regResult["error"]
	if ok {
		fmt.Println("Registration Error ", errCode, regResult["message"])
		return
	}

	ssmCmd := exec.Command(
		ssmCmdPath, "-register", "-y",
		"-id", regResult["activation-id"],
		"-code", regResult["activation-code"],
		"-i", regResult["managed-id"],
		"--region", regResult["region"])
	ssmOut, err := ssmCmd.CombinedOutput()

	if err != nil {
		fmt.Println("SSM Register Error", err, string(ssmOut))
		panic(err)
	}
	fmt.Println("SSM Agent Registered")

	// Use old upstart compatibility layer to work with systemd for now.
	svcCmdPath, err := exec.LookPath("service")

	svcCmd := exec.Command(svcCmdPath, "amazon-ssm-agent", "restart")
	svcOut, err := svcCmd.CombinedOutput()

	if err != nil {
		fmt.Println("Error starting ssm agent service", err, string(svcOut))
	}

}
