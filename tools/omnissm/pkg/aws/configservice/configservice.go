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

package configservice

import (
	"context"
	"encoding/json"
	"strconv"
	"sync"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/credentials/stscreds"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/configservice"
	"github.com/aws/aws-sdk-go/service/configservice/configserviceiface"
	"github.com/hashicorp/go-multierror"
	"github.com/pkg/errors"
	"golang.org/x/sync/errgroup"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/manager"
)

type Config struct {
	*aws.Config

	AssumeRole string
}

type ConfigService struct {
	configserviceiface.ConfigServiceAPI

	config *Config
}

func New(config *Config) *ConfigService {
	sess := session.New(config.Config)
	if config.AssumeRole != "" {
		config.Config.WithCredentials(stscreds.NewCredentials(sess, config.AssumeRole))
	}
	c := &ConfigService{
		ConfigServiceAPI: configservice.New(session.New(config.Config)),
		config:           config,
	}
	return c
}

func min(a, b int) int {
	if a <= b {
		return a
	}
	return b
}

func (c *ConfigService) BatchGetResourceConfig(resources map[string]string) ([]*manager.ConfigurationItem, error) {
	resourceKeys := make([]*configservice.ResourceKey, 0)
	for k, v := range resources {
		resourceKeys = append(resourceKeys, &configservice.ResourceKey{ResourceId: aws.String(k), ResourceType: aws.String(v)})
	}
	var mu sync.Mutex
	var g errgroup.Group
	items := make([]*manager.ConfigurationItem, 0)
	for i := 0; i < len(resourceKeys); i += 100 {
		batchResourceKeys := resourceKeys[i:min(i+100, len(resourceKeys))]
		g.Go(func() error {
			configurationItems, err := c.batchGetResourceConfig(batchResourceKeys)
			if err != nil {
				return err
			}
			mu.Lock()
			items = append(items, configurationItems...)
			mu.Unlock()
			return nil
		})
	}
	if err := g.Wait(); err != nil {
		return nil, err
	}
	return items, nil
}

func (c *ConfigService) batchGetResourceConfig(resourceKeys []*configservice.ResourceKey) ([]*manager.ConfigurationItem, error) {
	resp, err := c.ConfigServiceAPI.BatchGetResourceConfigWithContext(context.Background(), &configservice.BatchGetResourceConfigInput{
		ResourceKeys: resourceKeys,
	})
	if err != nil {
		return nil, err
	}
	var mErr error
	items := make([]*manager.ConfigurationItem, 0)
	for _, item := range resp.BaseConfigurationItems {
		var ci manager.ConfigurationItem
		if err := json.Unmarshal([]byte(*item.Configuration), &ci.Configuration); err != nil {
			mErr = multierror.Append(mErr, errors.Wrap(err, "cannot unmarshal ConfigurationItem"))
			continue
		}
		ci.AWSAccountId = *item.AccountId
		ci.ARN = *item.Arn
		ci.AvailabilityZone = *item.AvailabilityZone
		ci.AWSRegion = *item.AwsRegion
		ci.ConfigurationItemCaptureTime = (*item.ConfigurationItemCaptureTime).Format("2006-01-02T15:04:05Z")
		ci.ConfigurationItemStatus = *item.ConfigurationItemStatus
		ci.ConfigurationStateId, _ = strconv.ParseFloat(*item.ConfigurationStateId, 64)
		ci.ResourceCreationTime = (*item.ResourceCreationTime).Format("2006-01-02T15:04:05Z")
		ci.ResourceId = *item.ResourceId
		ci.ResourceType = *item.ResourceType
		if ci.Tags == nil {
			ci.Tags = make(map[string]string)
		}
		for _, tag := range ci.Configuration.Tags {
			ci.Tags[tag.Key] = tag.Value
		}
		items = append(items, &ci)
	}
	return items, mErr
}
