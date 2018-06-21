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

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-sdk-go/aws/request"
	"github.com/pkg/errors"
	"github.com/rs/zerolog/log"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/lambda"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/omnissm"
)

type registrationHandler struct {
	*omnissm.OmniSSM
}

func (r *registrationHandler) RequestActivation(ctx context.Context, req *omnissm.RegistrationRequest) (*omnissm.RegistrationResponse, error) {
	logger := log.With().Str("handler", "CreateRegistration").Logger()
	logger.Info().Interface("identity", req.Identity()).Msg("new registration request")
	entry, err, ok := r.OmniSSM.Registrations.Get(req.Identity().Hash())
	if err != nil {
		return nil, err
	}
	if ok {
		logger.Info().Interface("entry", entry).Msg("existing registration entry found")
		return &omnissm.RegistrationResponse{RegistrationEntry: *entry, Region: req.Identity().Region}, nil
	}
	activation, err := r.SSM.CreateActivation(req.Identity().Name())
	if err != nil {
		if r.OmniSSM.SQS != nil && request.IsErrorThrottle(err) || request.IsErrorRetryable(err) {
			sqsErr := r.OmniSSM.SQS.Send(&omnissm.DeferredActionMessage{
				Type:  omnissm.CreateActivation,
				Value: req.Identity(),
			})
			if sqsErr != nil {
				return nil, sqsErr
			}
			return nil, errors.Wrapf(err, "deferred action to SQS queue: %#v", r.OmniSSM.Config.QueueName)
		}
		return nil, err
	}
	entry = &omnissm.RegistrationEntry{
		Id:         req.Identity().Hash(),
		CreatedAt:  time.Now().UTC(),
		AccountId:  req.Identity().AccountId,
		Region:     req.Identity().Region,
		InstanceId: req.Identity().InstanceId,
		Activation: *activation,
		ManagedId:  "-",
	}
	if err := r.OmniSSM.Registrations.Put(entry); err != nil {
		if r.OmniSSM.SQS != nil && request.IsErrorThrottle(err) || request.IsErrorRetryable(err) {
			sqsErr := r.OmniSSM.SQS.Send(&omnissm.DeferredActionMessage{
				Type:  omnissm.PutRegistrationEntry,
				Value: entry,
			})
			if sqsErr != nil {
				return nil, sqsErr
			}
			return nil, errors.Wrapf(err, "deferred action to SQS queue: %#v", r.OmniSSM.Config.QueueName)
		}
		return nil, err
	}
	logger.Info().Interface("entry", entry).Msg("new registration entry created")
	return &omnissm.RegistrationResponse{RegistrationEntry: *entry, Region: req.Identity().Region}, nil
}

func (r *registrationHandler) UpdateRegistration(ctx context.Context, req *omnissm.RegistrationRequest) (*omnissm.RegistrationResponse, error) {
	logger := log.With().Str("handler", "UpdateRegistration").Logger()
	logger.Info().Interface("identity", req.Identity()).Msg("update registration request")
	id := req.Identity().Hash()
	entry, err, ok := r.OmniSSM.Registrations.Get(id)
	if err != nil {
		return nil, err
	}
	if !ok {
		logger.Info().Str("instanceName", req.Identity().Name()).Str("id", id).Msg("registration entry not found")
		return nil, errors.Wrapf(err, "entry not found: %#v", id)
	}
	logger.Info().Interface("entry", entry).Msg("registration entry found")
	if req.ManagedId != "" || req.ManagedId != "-" {
		entry.ManagedId = req.ManagedId
		if err := r.OmniSSM.Registrations.Update(entry); err != nil {
			return nil, err
		}
		logger.Info().Interface("entry", entry).Msg("registration entry updated")
	}
	return &omnissm.RegistrationResponse{RegistrationEntry: *entry}, nil
}

func main() {
	config, err := omnissm.ReadConfig("config.yaml")
	if err != nil {
		panic(err)
	}
	omni, err := omnissm.New(config)
	if err != nil {
		panic(err)
	}
	r := registrationHandler{omni}
	lambda.Start(func(ctx context.Context, req events.APIGatewayProxyRequest) (*events.APIGatewayProxyResponse, error) {
		switch req.Resource {
		case "/register":
			var registerReq omnissm.RegistrationRequest
			if err := json.Unmarshal([]byte(req.Body), &registerReq); err != nil {
				return nil, err
			}
			if err := registerReq.Verify(); err != nil {
				return nil, err
			}
			if !config.IsAuthorized(registerReq.Identity().AccountId) {
				return nil, errors.Errorf("account not authorized: %#v", registerReq.Identity().AccountId)
			}
			switch req.HTTPMethod {
			case "POST":
				return lambda.JSON(r.RequestActivation(ctx, &registerReq))
			case "PATCH":
				return lambda.JSON(r.UpdateRegistration(ctx, &registerReq))
			}
		}
		return nil, lambda.NotFoundError{fmt.Sprintf("cannot find resource %#v", req.Resource)}
	})
}
