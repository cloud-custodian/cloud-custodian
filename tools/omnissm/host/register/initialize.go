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
	"errors"
	"fmt"
	"io/ioutil"
	"log"
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

const (
	// LinuxSSMRegistrationPath Linux Path to Agent Registration State
	LinuxSSMRegistrationPath = "/var/lib/amazon/ssm/registration"

	// IdentityURL EC2 metadata server instance identity document
	IdentityURL = "http://169.254.169.254/latest/dynamic/instance-identity/document"

	// SignatureURL RSA SHA256 Signature of identity document
	SignatureURL = "http://169.254.169.254/latest/dynamic/instance-identity/signature"
)

// SSMHostInfo output of ssm-cli get-ubstabce-information
type SSMHostInfo struct {
	InstanceID     string `json:"instance-id"`
	Region         string `json:"region"`
	ReleaseVersion string `json:"release-version"`
}

// NodeInfo SSM Node Registration Information
type NodeInfo struct {
	BinSSMAgent     string
	BinSSMInfo      string
	BinService      string
	RegistrationURL string
	Identity        string
	Signature       string
	ManagedID       string
	netClient       *http.Client
}

// NewNodeInfo Constructor for SSM Node Info
func NewNodeInfo() (*NodeInfo, error) {

	ssmCmdPath, err := exec.LookPath("amazon-ssm-agent")
	if err != nil {
		return nil, errors.New("Package Missing - Error finding amazon-ssm-agent")
	}

	ssmInfoPath, err := exec.LookPath("ssm-cli")
	if err != nil {
		return nil, errors.New("Package Missing - Error finding ssm-cli")
	}

	svcCmdPath, err := exec.LookPath("service")
	if err != nil {
		return nil, errors.New("Service cmd missing - no upstart/systemd?")
	}

	registrationURL := os.Getenv("OMNISSM_URI")
	if len(registrationURL) < 1 {
		return nil, errors.New("Missing Registration Endpoint Env Var (OMNISSM_URI)")
	}

	identity, err := FetchContents(IdentityURL)
	if err != nil {
		return nil, err
	}
	signature, err := FetchContents(SignatureURL)
	if err != nil {
		return nil, err
	}

	return &NodeInfo{
		BinSSMAgent:     ssmCmdPath,
		BinSSMInfo:      ssmInfoPath,
		BinService:      svcCmdPath,
		RegistrationURL: registrationURL,
		Identity:        string(identity),
		Signature:       string(signature),
		netClient:       &http.Client{Timeout: time.Second * 10},
	}, nil

}

// IsRegistered Is the node registered with SSM
func (n *NodeInfo) IsRegistered() bool {
	// If we have a current registration for hybrid mode, exit
	agentRaw, err := ioutil.ReadFile(LinuxSSMRegistrationPath)
	if err == nil {
		agentReg := SSMAgentRegistration{}
		err = json.Unmarshal(agentRaw, &agentReg)
		if err == nil {
			if strings.HasPrefix(agentReg.ManagedInstanceID, "mi-") {
				n.ManagedID = agentReg.ManagedInstanceID
				return true

			}
		}
	}
	return false
}

// GetSSMInfo Return ssm agent node information
func (n *NodeInfo) GetSSMInfo() (*SSMHostInfo, error) {
	ssmInfoCmd := exec.Command(n.BinSSMInfo, "get-instance-information")
	ssmInfoOut, err := ssmInfoCmd.Output()
	if err != nil {
		return nil, err
	}

	ssmInfo := SSMHostInfo{}
	err = json.Unmarshal(ssmInfoOut, &ssmInfo)
	if err != nil {
		return nil, err
	}
	n.ManagedID = ssmInfo.InstanceID
	return &ssmInfo, nil
}

// Register Node with SSM via registration API
func (n *NodeInfo) Register() error {

	regSerial, err := json.Marshal(
		map[string]string{
			"provider":  "aws",
			"identity":  n.Identity,
			"signature": n.Signature,
		})

	if err != nil {
		return err
	}

	fmt.Println("Registration Request", string(regSerial))

	response, err := n.netClient.Post(
		n.RegistrationURL, "application/json", bytes.NewReader(regSerial))
	if err != nil {
		return err
	}
	regResultBody, err := ioutil.ReadAll(response.Body)
	if err != nil {
		return err
	}
	defer response.Body.Close()

	if response.StatusCode != 200 {
		return fmt.Errorf("Registration Error %s", regResultBody)
	}

	regResult := map[string]string{}

	err = json.Unmarshal(regResultBody, &regResult)
	if err != nil {
		return err
	}
	errCode, ok := regResult["error"]
	if ok {
		return fmt.Errorf("Registration Error %s %s", errCode, regResult["message"])
	}

	ssmCmd := exec.Command(
		n.BinSSMAgent, "-register", "-y",
		"-id", regResult["activation-id"],
		"-code", regResult["activation-code"],
		"-i", regResult["managed-id"],
		"--region", regResult["region"])
	ssmOut, err := ssmCmd.CombinedOutput()

	if err != nil {
		return fmt.Errorf("SSM Register Error %s %s", err, string(ssmOut))
	}

	svcCmd := exec.Command(n.BinService, "amazon-ssm-agent", "restart")
	svcOut, err := svcCmd.CombinedOutput()

	if err != nil {
		return fmt.Errorf("SSM agent restart error %s %s", err, svcOut)
	}

	return nil

}

// UpdateSSMID Record host SSM Id via the registration API
func (n *NodeInfo) UpdateSSMID() error {
	ssmInfo, err := n.GetSSMInfo()
	if err != nil {
		return err
	}

	idSerial, err := json.Marshal(map[string]string{
		"provider":   "aws",
		"identity":   n.Identity,
		"signature":  n.Signature,
		"managed-id": ssmInfo.InstanceID,
	})

	if err != nil {
		return err
	}

	idReq, err := http.NewRequest("PATCH", n.RegistrationURL, bytes.NewReader(idSerial))
	if err != nil {
		return err
	}

	idReq.Header.Set("Content-Type", "application/json")
	response, err := n.netClient.Do(idReq)
	if err != nil {
		return err
	}
	defer response.Body.Close()

	idResultBody, err := ioutil.ReadAll(response.Body)
	if err != nil {
		return err
	}

	if response.StatusCode != 200 {
		return fmt.Errorf("Error recording SSM Instance Id %s %s", err, idResultBody)
	}

	return nil
}

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

	node, err := NewNodeInfo()
	if err != nil {
		log.Fatalf("Error initializing node %s", err)
	}

	if node.IsRegistered() {
		log.Printf("Instance registered already - ManagedId: %s\n", node.ManagedID)
		return
	}

	log.Println("Registering Instance")
	err = node.Register()
	if err != nil {
		log.Fatalf("Error registering node %s", err)
	}

	err = node.UpdateSSMID()
	if err != nil {
		log.Fatalf("Error recording node ssm id %s", err)
	}

	log.Printf("Instance Registered - ManagedId: %s\n", node.ManagedID)
}
