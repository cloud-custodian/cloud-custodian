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

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go/aws/request"
	"github.com/pkg/errors"
	"github.com/rs/zerolog/log"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/configservice"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ssm"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/omnissm"
)

var (
	resourceTypes = map[string]struct{}{
		"AWS::EC2::Instance": struct{}{},
	}

	resourceStatusTypes = map[string]struct{}{
		"ResourceDeleted":    struct{}{},
		"ResourceDiscovered": struct{}{},
		"OK":                 struct{}{},
	}

	omni *omnissm.OmniSSM
)

func init() {
	config, err := omnissm.ReadConfig("config.yaml")
	if err != nil {
		panic(err)
	}
	omni, err = omnissm.New(config)
	if err != nil {
		panic(err)
	}
}

func handleConfigurationItemChange(detail configservice.ConfigurationItemDetail) error {
	entry, err, ok := omni.Registrations.Get(detail.ConfigurationItem.Hash())
	if err != nil {
		return err
	}
	if !ok {
		return errors.Errorf("registration entry not found: %#v", detail.ConfigurationItem.Name())
	}
	log.Info().Interface("entry", entry).Msg("existing registration entry found")
	if !ssm.IsManagedInstance(entry.ManagedId) {
		return errors.Errorf("ManagedId %#v invalid for %s/%s", entry.AccountId, entry.InstanceId)
	}
	switch detail.ConfigurationItem.ConfigurationItemStatus {
	case "ResourceDiscovered", "OK":
		tags := make(map[string]string)
		for k, v := range detail.ConfigurationItem.Tags {
			if !omni.HasResourceTag(k) {
				continue
			}
			tags[k] = v
		}
		resourceTags := &ssm.ResourceTags{
			ManagedId: entry.ManagedId,
			Tags:      tags,
		}
		err := omni.SSM.AddTagsToResource(resourceTags)
		if err != nil {
			if omni.SQS != nil && request.IsErrorThrottle(err) || request.IsErrorRetryable(err) {
				sqsErr := omni.SQS.Send(&omnissm.DeferredActionMessage{
					Type:  omnissm.AddTagsToResource,
					Value: resourceTags,
				})
				if sqsErr != nil {
					return sqsErr
				}
				return errors.Wrapf(err, "deferred action to SQS queue: %#v", omni.Config.QueueName)
			}
			return err
		}
		log.Info().Msgf("AddTagsToResource successful for %#v", entry.ManagedId)
		inv := &ssm.CustomInventory{
			TypeName:    "Custom:CloudInfo",
			ManagedId:   entry.ManagedId,
			CaptureTime: detail.ConfigurationItem.ConfigurationItemCaptureTime,
			Content:     configservice.ConfigurationItemContentMap(detail.ConfigurationItem),
		}
		err = omni.SSM.PutInventory(inv)
		if err != nil {
			if omni.SQS != nil && request.IsErrorThrottle(err) || request.IsErrorRetryable(err) {
				sqsErr := omni.SQS.Send(&omnissm.DeferredActionMessage{
					Type:  omnissm.PutInventory,
					Value: inv,
				})
				if sqsErr != nil {
					return sqsErr
				}
				return errors.Wrapf(err, "deferred action to SQS queue: %#v", omni.Config.QueueName)
			}
			return err
		}
		log.Info().Msgf("PutInventory successful for %#v", entry.ManagedId)
	case "ResourceDeleted":
		if err := omni.SSM.DeregisterManagedInstance(entry.ManagedId); err != nil {
			if omni.SQS != nil && request.IsErrorThrottle(err) || request.IsErrorRetryable(err) {
				sqsErr := omni.SQS.Send(&omnissm.DeferredActionMessage{
					Type:  omnissm.DeregisterManagedInstance,
					Value: entry.ManagedId,
				})
				if sqsErr != nil {
					return sqsErr
				}
				return errors.Wrapf(err, "deferred action to SQS queue: %#v", omni.Config.QueueName)
			}
			return err
		}
		log.Info().Msgf("Successfully deregistered instance: %#v", entry.ManagedId)
		if err := omni.Registrations.Delete(entry.Id); err != nil {
			return err
		}
		log.Info().Msgf("Successfully deleted registration entry: %#v", entry.ManagedId)
		if omni.Config.ResourceDeletedSNSTopic != "" {
			data, err := json.Marshal(map[string]interface{}{
				"ManagedId":    entry.ManagedId,
				"ResourceId":   detail.ConfigurationItem.ResourceId,
				"AWSAccountId": detail.ConfigurationItem.AWSAccountId,
				"AWSRegion":    detail.ConfigurationItem.AWSRegion,
			})
			if err != nil {
				return errors.Wrap(err, "cannot marshal SNS message")
			}
			if err := omni.SNS.Publish(omni.Config.ResourceDeletedSNSTopic, data); err != nil {
				return err
			}
		}
	}
	return nil
}

type cloudWatchEvent struct {
	Version    string                              `json:"version"`
	ID         string                              `json:"id"`
	DetailType string                              `json:"detail-type"`
	Source     string                              `json:"source"`
	AccountId  string                              `json:"account"`
	Time       time.Time                           `json:"time"`
	Region     string                              `json:"region"`
	Resources  []string                            `json:"resources"`
	Detail     configservice.CloudWatchEventDetail `json:"detail"`
}

func main() {
	lambda.Start(func(ctx context.Context, event cloudWatchEvent) (err error) {
		if event.Source != "aws.config" {
			return
		}
		switch event.Detail.MessageType {
		case "ConfigurationItemChangeNotification":
			if _, ok := resourceTypes[event.Detail.ConfigurationItem.ResourceType]; !ok {
				return
			}
			if _, ok := resourceStatusTypes[event.Detail.ConfigurationItem.ConfigurationItemStatus]; !ok {
				return
			}
			return handleConfigurationItemChange(event.Detail.ConfigurationItemDetail)
		case "OversizedConfigurationItemChangeNotification":
			if _, ok := resourceTypes[event.Detail.ConfigurationItemSummary.ResourceType]; !ok {
				return
			}
			if _, ok := resourceStatusTypes[event.Detail.ConfigurationItemSummary.ConfigurationItemStatus]; !ok {
				return
			}
			data, err := omni.S3.GetObject(event.Detail.S3DeliverySummary.S3BucketLocation)
			if err != nil {
				return err
			}
			var eventDetail configservice.ConfigurationItemDetail
			if err := json.Unmarshal(data, &eventDetail); err != nil {
				return err
			}
			return handleConfigurationItemChange(eventDetail)
		default:
			err = fmt.Errorf("unknown message type: %#v", event.Detail.MessageType)
		}
		return
	})
}
