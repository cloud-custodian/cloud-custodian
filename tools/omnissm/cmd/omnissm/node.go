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
	"os/exec"
	"time"

	"github.com/rs/zerolog/log"
)

type Config struct {
	Identity        InstanceIdentity
	RegistrationURL string
}

type Node struct {
	*http.Client

	config    *Config
	managedId string
}

// NewNode returns a new Node resource, representing an instance that can be
// registered and tracked by SSM.
func NewNode(c *Config) (*Node, error) {
	n := &Node{
		Client: &http.Client{Timeout: time.Second * 10},
		config: c,
	}
	var err error
	n.managedId, err = readRegistrationFile(DefaultLinuxSSMRegistrationPath)
	if err != nil {
		log.Debug().Err(err).Msg("cannot read SSM regisration file")
	}
	return n, nil
}

type RegisterRequest struct {
	Provider  string `json:"provider"`
	Identity  string `json:"identity"`
	Signature string `json:"signature"`
	ManagedId string `json:"managed-id,omitempty"`
}

type RegisterResponse struct {
	ActivationId   string `json:"activation-id"`
	ActivationCode string `json:"activation-code"`
	ManagedId      string `json:"managed-id"`
	Region         string `json:"region"`
	Error          string `json:"error"`
	Message        string `json:"message"`
}

// Register adds a Node/Resource to SSM via the register API
func (n *Node) Register() error {
	data, err := json.Marshal(RegisterRequest{
		Provider:  "aws",
		Identity:  n.config.Identity.Document,
		Signature: n.config.Identity.Signature,
	})
	if err != nil {
		return err
	}
	log.Info().Msgf("reqistration request: %#v", string(data))
	resp, err := n.Post(n.config.RegistrationURL, "application/json", bytes.NewReader(data))
	if err != nil {
		return err
	}
	data, err = ioutil.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return fmt.Errorf("register error: %#v", string(data))
	}
	var r RegisterResponse
	if err := json.Unmarshal(data, &r); err != nil {
		return err
	}
	if r.Error != "" {
		return fmt.Errorf("Registration Error %s %s", r.Error, r.Message)
	}
	out, err := exec.Command(SSMAgent.Path(), "-register", "-y",
		"-id", r.ActivationId,
		"-code", r.ActivationCode,
		"-i", r.ManagedId,
		"--region", r.Region).CombinedOutput()
	if err != nil {
		return fmt.Errorf("SSM Register Error %s %s", err, string(out))
	}
	return restartAgent()
}

// Update adds the instance id (managedId) via the register API
func (n *Node) Update() error {
	info, err := getInstanceInformation()
	if err != nil {
		return err
	}
	n.managedId = info.InstanceId
	data, err := json.Marshal(RegisterRequest{
		Provider:  "aws",
		Identity:  n.config.Identity.Document,
		Signature: n.config.Identity.Signature,
		ManagedId: info.InstanceId,
	})
	if err != nil {
		return err
	}
	req, err := http.NewRequest("PATCH", n.config.RegistrationURL, bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := n.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, err = ioutil.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if resp.StatusCode != 200 {
		return fmt.Errorf("Error recording SSM Instance Id %s %s", err, data)
	}
	return nil
}
