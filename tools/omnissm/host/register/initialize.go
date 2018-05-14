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
	"log"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/pkg/errors"
)

const (
	// LinuxSSMRegistrationPath Linux Path to Agent Registration State
	LinuxSSMRegistrationPath = "/var/lib/amazon/ssm/registration"

	// IdentityURL EC2 metadata server instance identity document
	IdentityURL = "http://169.254.169.254/latest/dynamic/instance-identity/document"

	// SignatureURL RSA SHA256 Signature of identity document
	SignatureURL = "http://169.254.169.254/latest/dynamic/instance-identity/signature"
)

// SSMAgentRegistration Sourced from /var/lib/amazon/ssm/registration
type SSMAgentRegistration struct {
	ManagedInstanceID string
	Region            string
}

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
	ServiceArgs     []string
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

	svcPath, err := exec.LookPath("systemctl")
	if err != nil {
		if e, ok := err.(*exec.Error); !(ok && e.Err == exec.ErrNotFound) {
			return nil, errors.Wrap(err, "Unable to find systemctl")
		}
	}
	serviceCmdArgs := []string{"amazon-ssm-agent", "restart"}

	if svcPath == "" {
		svcPath, err = exec.LookPath("initctl")
		if err != nil {
			return nil, errors.New("Package Missing - Error finding systemctl or initctl")
		}
		// initctl expects command first, then service name
		serviceCmdArgs = []string{"restart", "amazon-ssm-agent"}
	}

	registrationURL := os.Getenv("OMNISSM_URI")
	if len(registrationURL) < 1 {
		return nil, errors.New("Missing Registration Endpoint Env Var (OMNISSM_URI)")
	}

	n := NodeInfo{
		BinSSMAgent:     ssmCmdPath,
		BinSSMInfo:      ssmInfoPath,
		BinService:      svcPath,
		ServiceArgs:     serviceCmdArgs,
		RegistrationURL: registrationURL,
		netClient:       &http.Client{Timeout: 10 * time.Second},
	}

	// EC2 Metadata request for identity document
	b, err := readResponse(n.netClient.Get(IdentityURL))
	if err != nil {
		return nil, errors.Wrap(err, "instance identity request failed")
	}
	n.Identity = string(b)

	// EC2 Metadata request for signature
	b, err = readResponse(n.netClient.Get(SignatureURL))
	if err != nil {
		return nil, errors.Wrap(err, "instance signature request failed")
	}
	n.Signature = string(b)

	return &n, nil
}

// IsRegistered Is the node registered with SSM
func (n *NodeInfo) IsRegistered() bool {
	// If we have a current registration for hybrid mode, exit
	raw, err := ioutil.ReadFile(LinuxSSMRegistrationPath)
	if err == nil {
		var r SSMAgentRegistration
		if err := json.Unmarshal(raw, &r); err == nil {
			if strings.HasPrefix(r.ManagedInstanceID, "mi-") {
				n.ManagedID = r.ManagedInstanceID
				return true

			}
		}
	}
	return false
}

// GetSSMInfo Return ssm agent node information
func (n *NodeInfo) GetSSMInfo() (*SSMHostInfo, error) {
	cmd := exec.Command(n.BinSSMInfo, "get-instance-information")
	out, err := cmd.Output()
	if err != nil {
		return nil, err
	}

	info := SSMHostInfo{}
	err = json.Unmarshal(out, &info)
	if err != nil {
		return nil, err
	}
	if strings.HasPrefix(info.InstanceID, "mi-") {
		n.ManagedID = info.InstanceID
	}
	return &info, nil
}

// Register Node with SSM via registration API
func (n *NodeInfo) Register() error {
	regSerial, err := json.Marshal(map[string]string{
		"provider":  "aws",
		"identity":  n.Identity,
		"signature": n.Signature,
	})
	if err != nil {
		return err
	}

	fmt.Println("Registration Request", string(regSerial))

	b, err := readResponse(n.netClient.Post(n.RegistrationURL, "application/json", bytes.NewReader(regSerial)))
	if err != nil {
		return err
	}

	result := make(map[string]string)
	if err := json.Unmarshal(b, &result); err != nil {
		return err
	}
	if code, ok := result["error"]; ok {
		return errors.Errorf("%s: %s", code, result["message"])
	}

	ssmCmd := exec.Command(n.BinSSMAgent,
		"-register", "-y",
		"-id", result["activation-id"],
		"-code", result["activation-code"],
		"-i", result["managed-id"],
		"--region", result["region"])
	ssmOut, err := ssmCmd.CombinedOutput()
	if err != nil {
		return errors.Errorf("SSM agent command failed: %v - %s", err, string(ssmOut))
	}

	svcCmd := exec.Command(n.BinService, n.ServiceArgs...)
	svcOut, err := svcCmd.CombinedOutput()
	if err != nil {
		return errors.Errorf("SSM agent restart failed: %v - %s", err, string(svcOut))
	}
	return nil
}

// UpdateSSMID Record host SSM Id via the registration API
func (n *NodeInfo) UpdateSSMID() error {
	info, err := n.GetSSMInfo()
	if err != nil {
		return err
	}

	b, err := json.Marshal(map[string]string{
		"provider":   "aws",
		"identity":   n.Identity,
		"signature":  n.Signature,
		"managed-id": info.InstanceID,
	})
	if err != nil {
		return err
	}

	req, err := http.NewRequest("PATCH", n.RegistrationURL, bytes.NewReader(b))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	_, err = readResponse(n.netClient.Do(req))
	return err
}

func readResponse(resp *http.Response, err error) ([]byte, error) {
	if err != nil {
		// network error sending request
		return nil, err
	}
	defer resp.Body.Close()
	b, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != 200 {
		return nil, errors.Errorf("%d: %s", resp.StatusCode, string(b))
	}
	return b, nil
}

func main() {
	node, err := NewNodeInfo()
	if err != nil {
		log.Fatalf("Error initializing node: %v", err)
	}

	if node.IsRegistered() {
		log.Printf("Instance registered already - ManagedId: %s\n", node.ManagedID)
		return
	}

	log.Println("Registering Instance")
	err = node.Register()
	if err != nil {
		log.Fatalf("Error registering node: %v", err)
	}

	err = node.UpdateSSMID()
	if err != nil {
		log.Fatalf("Error recording node ssm id: %v", err)
	}

	log.Printf("Instance Registered - ManagedId: %s\n", node.ManagedID)
}
