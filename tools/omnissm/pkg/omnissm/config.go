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
	"context"
	"fmt"
	"io/ioutil"
	"os"
	"strconv"
	"strings"

	"github.com/aws/aws-sdk-go/aws"
	version "github.com/hashicorp/go-version"
	"github.com/pkg/errors"
	"gopkg.in/yaml.v2"
)

const DefaultSSMServiceRole = "service-role/AmazonEC2RunCommandRoleForManagedInstances"

type Config struct {
	*aws.Config

	Context context.Context

	// A whitelist of accounts allowed to register with SSM
	AccountWhitelist []string `yaml:"accountWhitelist"`

	// This or AssumeRoles must be specified.
	AssumeRoleName string `yaml:"assumeRole"`

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

	// The SNS topic published to when resources are registered (optional).
	ResourceRegisteredSNSTopic string `yaml:"resourceRegisteredSNSTopic"`

	// The SNS topic published to when resources are deleted (optional).
	ResourceDeletedSNSTopic string `yaml:"resourceDeletedSNSTopic"`

	// The name of tags that should be added to SSM tags if they are tagged on
	// the EC2 instance.
	ResourceTags []string `yaml:"resourceTags"`

	// The IAM role used for downloading Oversized ConfigurationItems from S3.
	S3DownloadRole string `yaml:"s3DownloadRole"`

	// The IAM role used for publishing to the Resource Deleted SNS topic (optional).
	SNSPublishRole string `yaml:"snsPublishRole"`

	// This is set by AWS when a Lambda instance is configured to use x-ray.
	// This is optional and x-ray is currently only supported when using lambda.
	XRayTracingEnabled string `yaml:"xrayTracingEnabled"`

	// The number of days to wait to clean up registered ssm instances that have a
	// PingStatus of ConnectionLost
	CleanupAfterDays float64 `yaml:"cleanupAfterDays"`

	// Version constraints for allowable client requests during registration. If
	// constraints are empty, all versions are allowed. Version string should
	// conform with github.com/hashicorp/go-version format, i.e. comma-separated
	// rules like ">= 1.1.0, < 2.0.0"
	ClientVersionConstraints string `yaml:"clientVersionConstraints"`

	authorizedAccountIds map[string]struct{}
	resourceTags         map[string]struct{}
	roleMap              map[string]string
	versionConstraint    version.Constraints
}

func NewConfig() *Config {
	c := &Config{}
	MergeConfig(c, ReadConfigFromEnv())
	return c
}

// ReadConfig loads configuration values from a yaml file.
// The priority of the sources is the following:
// 1. flags
// 2. environment variables
// 3. config file
// 4. defaults
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
	MergeConfig(&c, ReadConfigFromEnv())
	c.setDefaults()
	return &c, nil
}

// splitNonEmpty returns a nil slice when s is blank
func splitNonEmpty(s string, sep string) []string {
	if s == "" {
		return nil
	}
	return strings.Split(s, sep)
}

func ReadConfigFromEnv() *Config {
	maxRetries, _ := strconv.Atoi(os.Getenv("OMNISSM_MAX_RETRIES"))
	c := &Config{
		AccountWhitelist:           splitNonEmpty(os.Getenv("OMNISSM_ACCOUNT_WHITELIST"), ","),
		InstanceRole:               os.Getenv("OMNISSM_INSTANCE_ROLE"),
		MaxRetries:                 maxRetries,
		RegistrationsTable:         os.Getenv("OMNISSM_REGISTRATIONS_TABLE"),
		QueueName:                  os.Getenv("OMNISSM_SPILLOVER_QUEUE"),
		ResourceRegisteredSNSTopic: os.Getenv("OMNISSM_RESOURCE_REGISTERED_SNS_TOPIC"),
		ResourceDeletedSNSTopic:    os.Getenv("OMNISSM_RESOURCE_DELETED_SNS_TOPIC"),
		ResourceTags:               splitNonEmpty(os.Getenv("OMNISSM_RESOURCE_TAGS"), ","),
		S3DownloadRole:             os.Getenv("OMNISSM_S3_DOWNLOAD_ROLE"),
		SNSPublishRole:             os.Getenv("OMNISSM_SNS_PUBLISH_ROLE"),
		XRayTracingEnabled:         os.Getenv("_X_AMZN_TRACE_ID"),
	}
	return c
}

func MergeConfig(config *Config, other *Config) {
	if len(other.AccountWhitelist) > 0 {
		config.AccountWhitelist = other.AccountWhitelist
		config.authorizedAccountIds = nil
	}
	if other.InstanceRole != "" {
		config.InstanceRole = other.InstanceRole
	}
	if other.MaxRetries != 0 {
		config.MaxRetries = other.MaxRetries
	}
	if other.QueueName != "" {
		config.QueueName = other.QueueName
	}
	if other.RegistrationsTable != "" {
		config.RegistrationsTable = other.RegistrationsTable
	}
	if other.ResourceRegisteredSNSTopic != "" {
		config.ResourceRegisteredSNSTopic = other.ResourceRegisteredSNSTopic
	}
	if other.ResourceDeletedSNSTopic != "" {
		config.ResourceDeletedSNSTopic = other.ResourceDeletedSNSTopic
	}
	if len(other.ResourceTags) > 0 {
		config.ResourceTags = other.ResourceTags
		config.resourceTags = nil
	}
	if other.S3DownloadRole != "" {
		config.S3DownloadRole = other.S3DownloadRole
	}
	if other.SNSPublishRole != "" {
		config.SNSPublishRole = other.SNSPublishRole
	}
	if other.ClientVersionConstraints != "" {
		config.ClientVersionConstraints = other.ClientVersionConstraints
	}
	config.setDefaults()
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
	if c.ClientVersionConstraints != "" {
		cs, err := version.NewConstraint(c.ClientVersionConstraints)
		if err == nil {
			c.versionConstraint = cs
		}
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
	if c.resourceTags == nil {
		c.resourceTags = make(map[string]struct{})
	}
	for _, t := range c.ResourceTags {
		c.resourceTags[t] = struct{}{}
	}
	c.Config = aws.NewConfig().WithMaxRetries(c.MaxRetries)
}

func (c *Config) RequestVersionValid(vs string) bool {
	if c.versionConstraint == nil {
		return true
	} else if vs == "" {
		return false
	}
	v, err := version.NewVersion(vs)
	if err != nil {
		return false
	}
	return c.versionConstraint.Check(v)
}

func (c *Config) HasAssumeRole(accountId string) (roleArn string, ok bool) {
	if c.AssumeRoleName != "" {
		return fmt.Sprintf("arn:aws:iam::%s:role/%s", accountId, c.AssumeRoleName), true
	}
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
