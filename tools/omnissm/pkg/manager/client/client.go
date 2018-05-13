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

package client

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"os/exec"
	"time"

	"github.com/pkg/errors"
	"github.com/rs/zerolog/log"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/api"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/identity"
)

type Config struct {
	Document        string
	Signature       string
	RegistrationURL string
}

type Client struct {
	*http.Client

	config    *Config
	managedId string
}

// NewClient returns a new client for registering/updating managed resources.
func NewClient(config *Config) (*Client, error) {
	c := &Client{
		Client: &http.Client{Timeout: time.Second * 10},
		config: config,
	}
	var err error
	c.managedId, err = readRegistrationFile(DefaultLinuxSSMRegistrationPath)
	if err != nil {
		log.Debug().Err(err).Msg("cannot read SSM regisration file")
	}
	return c, nil
}

func (c *Client) ManagedId() string {
	return c.managedId
}

// Register adds a Node/Resource to SSM via the register API
func (c *Client) Register() error {
	data, err := json.Marshal(api.RegisterRequest{
		Provider:  "aws",
		Document:  []byte(c.config.Document),
		Signature: c.config.Signature,
	})
	if err != nil {
		return err
	}
	log.Info().Msgf("reqistration request: %#v", string(data))
	resp, err := c.Post(c.config.RegistrationURL, "application/json", bytes.NewReader(data))
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
	var r api.RegisterResponse
	if err := json.Unmarshal(data, &r); err != nil {
		return err
	}
	if r.Err() != nil {
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
func (c *Client) Update() error {
	info, err := GetInstanceInformation()
	if err != nil {
		return err
	}
	if !identity.IsManagedInstance(info.InstanceId) {
		return errors.Errorf("cannot update node, not a managed instance: %#v", info.InstanceId)
	}
	c.managedId = info.InstanceId
	data, err := json.Marshal(api.RegisterRequest{
		Provider:  "aws",
		Document:  []byte(c.config.Document),
		Signature: c.config.Signature,
		ManagedId: info.InstanceId,
	})
	if err != nil {
		return err
	}
	req, err := http.NewRequest("PATCH", c.config.RegistrationURL, bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.Do(req)
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
