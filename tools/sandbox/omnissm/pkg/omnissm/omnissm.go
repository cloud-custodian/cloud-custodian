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
	"encoding/json"
	"time"

	"github.com/aws/aws-sdk-go/aws/request"
	"github.com/pkg/errors"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/s3"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/sns"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/sqs"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ssm"
)

type OmniSSM struct {
	*Config
	*Registrations
	*s3.S3
	*sns.SNS
	*sqs.SQS
	*ssm.SSM
}

func New(config *Config) (*OmniSSM, error) {
	o := &OmniSSM{
		Config: config,
		Registrations: NewRegistrations(&RegistrationsConfig{
			Config:    config.Config,
			TableName: config.RegistrationsTable,
		}),
		SNS: sns.New(&sns.Config{
			Config:     config.Config,
			AssumeRole: config.S3DownloadRole,
		}),
		SSM: ssm.New(&ssm.Config{
			Config:       config.Config,
			InstanceRole: config.InstanceRole,
		}),
		S3: s3.New(&s3.Config{
			Config:     config.Config,
			AssumeRole: config.S3DownloadRole,
		}),
	}
	if config.QueueName != "" {
		var err error
		o.SQS, err = sqs.New(&sqs.Config{
			Config:         config.Config,
			MessageGroupId: "omnissm-event-stream",
			QueueName:      config.QueueName,
		})

		if err != nil {
			return nil, errors.Wrap(err, "cannot initialize SQS")
		}
	}

	if config.XRayTracingEnabled != "" {
		SetupTracing(o)
	}

	return o, nil
}

func (o *OmniSSM) RequestActivation(ctx context.Context, req *RegistrationRequest) (*RegistrationResponse, error) {
	entry, err, ok := o.Registrations.Get(ctx, req.Identity().Hash())
	if err != nil {
		return nil, err
	}
	if ok && (ssm.IsManagedInstance(entry.ManagedId) || time.Now().Sub(entry.CreatedAt) < 12*time.Hour) {
		// duplicate request
		return &RegistrationResponse{RegistrationEntry: *entry, Region: req.Identity().Region, existing: true}, nil
	}
	activation, err := o.SSM.CreateActivation(ctx, req.Identity().Name())
	if err != nil {
		// if we fail here, defer starting over
		return nil, o.tryDefer(ctx, err, RequestActivation, req)
	}
	entry = &RegistrationEntry{
		Id:            req.Identity().Hash(),
		CreatedAt:     time.Now().UTC(),
		AccountId:     req.Identity().AccountId,
		Region:        req.Identity().Region,
		InstanceId:    req.Identity().InstanceId,
		ClientVersion: req.ClientVersion,
		Activation:    *activation,
		ManagedId:     "-",
	}
	if err := o.Registrations.Put(ctx, entry); err != nil {
		// if we fail here, defer saving the created activation to alleviate
		// pressure on SSM to create it again
		return nil, o.tryDefer(ctx, err, PutRegistrationEntry, entry)
	}
	return &RegistrationResponse{RegistrationEntry: *entry, Region: req.Identity().Region}, nil
}

func (o *OmniSSM) DeregisterInstance(ctx context.Context, entry *RegistrationEntry) error {
	if err := o.SSM.DeregisterManagedInstance(ctx, entry.ManagedId); err != nil {
		// if we fail here, defer starting over
		return o.tryDefer(ctx, err, DeregisterInstance, entry)
	}
	if err := o.Registrations.Delete(ctx, entry.Id); err != nil {
		// if we fail here, defer starting over
		return o.tryDefer(ctx, err, DeleteRegistrationEntry, entry.Id)
	}
	if o.Config.ResourceDeletedSNSTopic != "" {
		data, err := json.Marshal(map[string]interface{}{
			"ManagedId":    entry.ManagedId,
			"ResourceId":   entry.InstanceId,
			"AWSAccountId": entry.AccountId,
			"AWSRegion":    entry.Region,
		})
		if err != nil {
			return errors.Wrap(err, "cannot marshal SNS message")
		}
		if err := o.SNS.Publish(ctx, o.Config.ResourceDeletedSNSTopic, data); err != nil {
			return err
		}
	}
	return nil
}

func (o *OmniSSM) tryDefer(ctx context.Context, err error, t DeferredActionType, value interface{}) error {
	if o.SQS != nil && request.IsErrorThrottle(err) || request.IsErrorRetryable(err) {
		sqsErr := o.SQS.Send(ctx, &DeferredActionMessage{
			Type:  t,
			Value: value,
		})
		if sqsErr != nil {
			return errors.Wrapf(sqsErr, "could not defer message (original error: %v)", err)
		}
		return errors.Wrapf(err, "deferred action to SQS queue (%s)", o.Config.QueueName)
	}
	return err
}
