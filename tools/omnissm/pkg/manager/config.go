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

package manager

import (
	"fmt"
	"io/ioutil"
	"os"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/pkg/errors"
	"gopkg.in/yaml.v2"
)

const DefaultSSMServiceRole = "service-role/AmazonEC2RunCommandRoleForManagedInstances"

type Config struct {
	*aws.Config

	// A whitelist of accounts allowed to register with SSM
	AccountWhitelist []string `yaml:"accountWhitelist"`

	// A mapping of IAM roles to assume with the provided accounts
	AssumeRoles map[string]string `yaml:"assumeRoles"`

	// The IAM role used when the SSM agent registers with the SSM service
	InstanceRole string `yaml:"instanceRole"`

	// Sets the number of retries attempted for AWS API calls. Defaults to 0
	// if not specified.
	MaxRetries int `yaml:"maxRetries"`

	// If provided, SSM API requests that are throttled will be sent to this
	// queue. Should be used in conjunction with MaxRetries since the
	// throttling that takes place should retry several times before attempting
	// to queue the request.
	QueueName string `yaml:"queueName"`

	// The DynamodDb table used for storing instance regisrations.
	RegistrationsTable string `yaml:"registrationsTable"`

	// The name of tags that should be added to SSM tags if they are tagged on
	// the EC2 instance.
	ResourceTags []string `yaml:"resourceTags"`

	authorizedAccountIds map[string]struct{}
	resourceTags         map[string]struct{}
	roleMap              map[string]string
}

func ReadConfig(path string) (*Config, error) {
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return nil, errors.Wrapf(err, "%#v not found", path)
	}
	data, err := ioutil.ReadFile(path)
	if err != nil {
		return nil, errors.Wrapf(err, "cannot read file: %#v", path)
	}

	var c Config
	if err := yaml.Unmarshal(data, &c); err != nil {
		return nil, errors.Wrap(err, "cannot unmarshal")
	}
	c.setDefaults()
	return &c, nil
}

func (c *Config) setDefaults() {
	if c.InstanceRole == "" {
		c.InstanceRole = DefaultSSMServiceRole
	}
	if c.RegistrationsTable == "" {
		c.RegistrationsTable = "omnissm-registrations"
	}
	if len(c.ResourceTags) == 0 {
		c.ResourceTags = []string{"App", "OwnerContact", "Name"}
	}
	if c.roleMap == nil {
		c.roleMap = make(map[string]string)
	}
	for accountId, roleName := range c.AssumeRoles {
		c.roleMap[accountId] = fmt.Sprintf("arn:aws:iam::%s:role/%s", accountId, roleName)
	}
	if c.authorizedAccountIds == nil {
		c.authorizedAccountIds = make(map[string]struct{})
	}
	for _, accountId := range c.AccountWhitelist {
		c.authorizedAccountIds[accountId] = struct{}{}
	}
	for _, t := range c.ResourceTags {
		c.resourceTags[t] = struct{}{}
	}
	c.Config = aws.NewConfig().WithMaxRetries(c.MaxRetries)
}

func (c *Config) HasAssumeRole(accountId string) (roleArn string, ok bool) {
	roleArn, ok = c.roleMap[accountId]
	return
}
func (c *Config) HasResourceTag(tagName string) (ok bool) {
	_, ok = c.resourceTags[tagName]
	return
}

func (c *Config) IsAuthorized(accountId string) (ok bool) {
	_, ok = c.authorizedAccountIds[accountId]
	return
}
