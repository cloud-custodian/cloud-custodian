// Copyright 2018 Capital One Services, LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package omnissm

import (
	"bytes"
	"encoding/json"
	"io/ioutil"
	"net/http"
	"os/exec"
	"time"

	"github.com/pkg/errors"
	"github.com/rs/zerolog/log"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ec2metadata"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ssm"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/servicectl"
)

type Client struct {
	*http.Client

	document, signature string
	registrationURL     string
	ManagedId           string

	service servicectl.Service
}

// New returns a new client for the registrations API
func NewClient(url string) (*Client, error) {
	s, err := servicectl.New("amazon-ssm-agent")
	if err != nil {
		return nil, err
	}
	c := &Client{
		Client:          &http.Client{Timeout: time.Second * 10},
		document:        string(ec2metadata.GetLocalInstanceDocument()),
		signature:       string(ec2metadata.GetLocalInstanceSignature()),
		registrationURL: url,
		service:         s,
	}
	c.ManagedId, _ = ssm.ReadRegistrationFile(ssm.DefaultLinuxSSMRegistrationPath)
	return c, nil
}

// Register requests an activation from the registrations API and attempts to
// register the current instance with SSM. A new activation will be created
// should an existing one not be found in the registrations table.
func (c *Client) Register() error {
	data, err := json.Marshal(RegistrationRequest{
		Provider:  "aws",
		Document:  c.document,
		Signature: c.signature,
	})
	if err != nil {
		return errors.Wrap(err, "cannot marshal new registration request")
	}
	log.Info().Msgf("registration request: %#v", string(data))
	resp, err := c.Post(c.registrationURL, "application/json", bytes.NewReader(data))
	if err != nil {
		return err
	}
	data, err = ioutil.ReadAll(resp.Body)
	if err != nil {
		return errors.WithStack(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return errors.Errorf("cannot register new resource: %d, %s", resp.StatusCode, string(data))
	}
	var r RegistrationResponse
	if err := json.Unmarshal(data, &r); err != nil {
		return errors.WithStack(err)
	}
	cmd, err := exec.LookPath("amazon-ssm-agent")
	if err != nil {
		return errors.WithStack(err)
	}
	out, err := exec.Command(cmd, "-register", "-y",
		"-id", r.ActivationId,
		"-code", r.ActivationCode,
		"-i", r.ManagedId,
		"--region", r.Region).CombinedOutput()
	if err != nil {
		return errors.Wrapf(err, "amazon-ssm-agent failed: %v\noutput: %s", err, string(out))
	}
	return c.service.Restart()
}

// Update attempts to update the ManagedId in the registrations table
func (c *Client) Update() error {
	info, err := ssm.GetInstanceInformation()
	if err != nil {
		return err
	}
	if !ssm.IsManagedInstance(info.InstanceId) {
		return errors.Errorf("cannot update node, not a managed instance: %#v", info.InstanceId)
	}
	c.ManagedId = info.InstanceId
	data, err := json.Marshal(RegistrationRequest{
		Provider:  "aws",
		Document:  c.document,
		Signature: c.signature,
		ManagedId: info.InstanceId,
	})
	if err != nil {
		return errors.Wrap(err, "cannot marshal registration request")
	}
	req, err := http.NewRequest("PATCH", c.registrationURL, bytes.NewReader(data))
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
		return errors.Wrap(err, "cannot read body for Register/Update")
	}
	if resp.StatusCode != 200 {
		return errors.Errorf("cannot update ManagedId: %d, %s", resp.StatusCode, string(data))
	}
	return nil
}
