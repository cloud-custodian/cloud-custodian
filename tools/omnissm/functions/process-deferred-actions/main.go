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

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go/aws/awserr"
	"github.com/pkg/errors"
	"github.com/rs/zerolog/log"

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

func processDeferredActionMessage(ctx context.Context, msg *sqs.Message) error {
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
		if err := omni.SSM.AddTagsToResource(ctx, &resourceTags); err != nil {
			if awsErr, ok := errors.Cause(err).(awserr.Error); ok {
				if awsErr.Code() == "InvalidResourceId" {
					log.Warn().Err(err).Msg("instance no longer exists")
					return nil
				}
			}
			return err
		} else {
			log.Info().Msg("tags added to resource successfully")
			entry, err, ok := omni.Registrations.GetByManagedId(ctx, resourceTags.ManagedId)
			if err != nil {
				return err
			}
			if !ok {
				return errors.Errorf("registration entry not found: %#v", resourceTags.ManagedId)
			}
			entry.IsTagged = 1
			if err := omni.Registrations.Update(ctx, entry); err != nil {
				return err
			}
		}
	case omnissm.RequestActivation:
		var req omnissm.RegistrationRequest
		if err := json.Unmarshal(dMsg.Value, &req); err != nil {
			return errors.Wrap(err, "cannot unmarshal DeferredActionMessage.Value")
		}
		resp, err := omni.RequestActivation(ctx, &req)
		if err != nil {
			return err
		}
		if resp.Existing() {
			log.Info().Interface("entry", resp).Msg("existing registration entry found")
		} else {
			log.Info().Interface("entry", resp).Msg("new registration entry created")
		}
	case omnissm.DeregisterInstance:
		var entry omnissm.RegistrationEntry
		if err := json.Unmarshal(dMsg.Value, &entry); err != nil {
			return errors.Wrap(err, "cannot unmarshal DeferredActionMessage.Value")
		}
		_, err, ok := omni.Registrations.Get(ctx, entry.Id)
		if err != nil {
			// Get failure here means the instance will not be deregistered,
			// needs to be cleaned up by another process
			return err
		}
		if !ok {
			return errors.Errorf("registration entry not found: %#v", entry.Id)
		}
		if !ssm.IsManagedInstance(entry.ManagedId) {
			return errors.Errorf("registration managed id is invalid: %#v", entry.ManagedId)
		}
		if err := omni.DeregisterInstance(ctx, &entry); err != nil {
			return err
		}
	case omnissm.PutInventory:
		var inv ssm.CustomInventory
		if err := json.Unmarshal(dMsg.Value, &inv); err != nil {
			return errors.Wrap(err, "cannot unmarshal DeferredActionMessage.Value")
		}
		if err := omni.SSM.PutInventory(ctx, &inv); err != nil {
			if awsErr, ok := errors.Cause(err).(awserr.Error); ok {
				if awsErr.Code() == "InvalidResourceId" {
					log.Warn().Err(err).Msg("instance no longer exists")
					return nil
				}
			}
			return err
		}
		log.Info().Msg("custom inventory successful")
		entry, err, ok := omni.Registrations.GetByManagedId(ctx, inv.ManagedId)
		if err != nil {
			return err
		}
		if !ok {
			return errors.Errorf("registration entry not found: %#v", inv.ManagedId)
		}
		entry.IsInventoried = 1
		if err := omni.Registrations.Update(ctx, entry); err != nil {
			return err
		}
	case omnissm.PutRegistrationEntry:
		var entry omnissm.RegistrationEntry
		if err := json.Unmarshal(dMsg.Value, &entry); err != nil {
			return errors.Wrap(err, "cannot unmarshal DeferredActionMessage.Value")
		}
		if err := omni.Registrations.Put(ctx, &entry); err != nil {
			return err
		}
		log.Info().Interface("entry", entry).Msg("new registration entry created")
	case omnissm.DeleteRegistrationEntry:
		var id string
		if err := json.Unmarshal(dMsg.Value, &id); err != nil {
			return errors.Wrap(err, "cannot unmarshal DeferredActionMessage.Value")
		}
		if err := omni.Registrations.Delete(ctx, id); err != nil {
			return err
		}
		log.Info().Msgf("Successfully deleted registration entry: %#v", id)
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
				resp, err := omni.SQS.Receive(ctx)
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
				if err := processDeferredActionMessage(ctx, m); err != nil {
					log.Info().Err(err).Interface("message", m).Msg("processing DeferredActionMessage failed")
				}
				if err := omni.SQS.Delete(ctx, m.ReceiptHandle); err != nil {
					log.Info().Err(err).Interface("message", m).Msg("removing from SQS queue failed")
				}
			case <-ctx.Done():
				return nil
			}
		}
		return nil
	})
}
