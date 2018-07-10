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
	"time"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go/aws/request"
	"github.com/pkg/errors"
	"github.com/rs/zerolog/log"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ec2metadata"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/sqs"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ssm"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/omnissm"
)

var omni *omnissm.OmniSSM

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

func processDeferredActionMessage(msg *sqs.Message) error {
	var dMsg struct {
		Type  omnissm.DeferredActionType
		Value json.RawMessage
	}
	if err := json.Unmarshal([]byte(msg.Body), &dMsg); err != nil {
		return errors.Wrap(err, "cannot unmarshal DeferredActionMessage")
	}
	switch dMsg.Type {
	case omnissm.AddTagsToResource:
		var resourceTags ssm.ResourceTags
		if err := json.Unmarshal(dMsg.Value, &resourceTags); err != nil {
			return errors.Wrap(err, "cannot unmarshal DeferredActionMessage.Value")
		}
		if err := omni.SSM.AddTagsToResource(&resourceTags); err != nil {
			return err
		}
		log.Info().Msg("tags added to resource successfully")
		entry, err, ok := omni.Registrations.GetByManagedId(resourceTags.ManagedId)
		if err != nil {
			return err
		}
		if !ok {
			return errors.Errorf("registration entry not found: %#v", resourceTags.ManagedId)
		}
		entry.IsTagged = true
		if err := omni.Registrations.Update(entry); err != nil {
			return err
		}
	case omnissm.CreateActivation:
		var doc ec2metadata.Document
		if err := json.Unmarshal(dMsg.Value, &doc); err != nil {
			return errors.Wrap(err, "cannot unmarshal DeferredActionMessage.Value")
		}
		activation, err := omni.SSM.CreateActivation(doc.Name())
		if err != nil {
			return err
		}
		entry := &omnissm.RegistrationEntry{
			Id:         doc.Hash(),
			CreatedAt:  time.Now().UTC(),
			AccountId:  doc.AccountId,
			Region:     doc.Region,
			InstanceId: doc.InstanceId,
			Activation: *activation,
		}
		if err := omni.Registrations.Put(entry); err != nil {
			if omni.SQS != nil && request.IsErrorThrottle(err) || request.IsErrorRetryable(err) {
				sqsErr := omni.SQS.Send(&omnissm.DeferredActionMessage{
					Type:  omnissm.PutRegistrationEntry,
					Value: entry,
				})
				if sqsErr != nil {
					return sqsErr
				}
				return errors.Wrapf(err, "deferred action to SQS queue: %#v", omni.Config.QueueName)
			}
			return err
		}
		log.Info().Interface("entry", entry).Msg("new registration entry created")
	case omnissm.DeregisterManagedInstance:
		var managedId string
		if err := json.Unmarshal(dMsg.Value, &managedId); err != nil {
			return errors.Wrap(err, "cannot unmarshal DeferredActionMessage.Value")
		}
		if err := omni.SSM.DeregisterManagedInstance(managedId); err != nil {
			return err
		}
	case omnissm.PutInventory:
		var inv ssm.CustomInventory
		if err := json.Unmarshal(dMsg.Value, &inv); err != nil {
			return errors.Wrap(err, "cannot unmarshal DeferredActionMessage.Value")
		}
		if err := omni.SSM.PutInventory(&inv); err != nil {
			return err
		}
		log.Info().Msg("custom inventory successful")
		entry, err, ok := omni.Registrations.GetByManagedId(inv.ManagedId)
		if err != nil {
			return err
		}
		if !ok {
			return errors.Errorf("registration entry not found: %#v", inv.ManagedId)
		}
		entry.IsInventoried = true
		if err := omni.Registrations.Update(entry); err != nil {
			return err
		}
	case omnissm.PutRegistrationEntry:
		var entry omnissm.RegistrationEntry
		if err := json.Unmarshal(dMsg.Value, &entry); err != nil {
			return errors.Wrap(err, "cannot unmarshal DeferredActionMessage.Value")
		}
		if err := omni.Registrations.Put(&entry); err != nil {
			return err
		}
		log.Info().Interface("entry", entry).Msg("new registration entry created")
	default:
	}
	return nil
}

func main() {
	lambda.Start(func(ctx context.Context) error {
		ctx, cancel := context.WithCancel(ctx)
		defer cancel()
		messages := make(chan *sqs.Message)
		go func() {
			defer close(messages)
			for {
				resp, err := omni.SQS.Receive()
				if err != nil {
					log.Info().Err(err).Msg("cannot receive from SQS queue")
					continue
				}
				if len(resp) == 0 {
					cancel()
					return
				}
				for _, m := range resp {
					messages <- m
				}
			}
		}()

		for {
			select {
			case m, ok := <-messages:
				if !ok {
					return nil
				}
				if err := processDeferredActionMessage(m); err != nil {
					log.Info().Err(err).Interface("message", m).Msg("processing DeferredActionMessage failed")
				}
				if err := omni.SQS.Delete(m.ReceiptHandle); err != nil {
					log.Info().Err(err).Interface("message", m).Msg("removing from SQS queue failed")
				}
			case <-ctx.Done():
				return nil
			}
		}
		return nil
	})
}
