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

	"github.com/aws/aws-lambda-go/events"
	"github.com/rs/zerolog/log"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/lambda"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ssm"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/omnissm"
)

type registrationHandler struct {
	*omnissm.OmniSSM
}

func (r *registrationHandler) RequestActivation(ctx context.Context, req *omnissm.RegistrationRequest) (*omnissm.RegistrationResponse, error) {
	logger := log.With().Str("handler", "RequestActivation").Logger()
	logger.Info().Interface("identity", req.Identity()).Msg("new registration request")
	resp, err := r.OmniSSM.RequestActivation(ctx, req)
	if err != nil {
		return nil, err
	}
	if resp.Existing() {
		logger.Info().Interface("entry", resp).Msg("existing registration entry found")
	} else {
		logger.Info().Interface("entry", resp).Msg("new registration entry created")
	}
	return resp, nil
}

func (r *registrationHandler) UpdateRegistration(ctx context.Context, req *omnissm.RegistrationRequest) (*omnissm.RegistrationResponse, error) {
	logger := log.With().Str("handler", "UpdateRegistration").Logger()
	logger.Info().Interface("identity", req.Identity()).Msg("update registration request")
	if !ssm.IsManagedInstance(req.ManagedId) {
		return nil, lambda.BadRequestError{fmt.Sprintf("invalid managedId %#v", req.ManagedId)}
	}
	id := req.Identity().Hash()
	entry, err, ok := r.OmniSSM.Registrations.Get(ctx, id)
	if err != nil {
		return nil, err
	}
	if !ok {
		logger.Info().Str("instanceName", req.Identity().Name()).Str("id", id).Msg("registration entry not found")
		return nil, lambda.NotFoundError{fmt.Sprintf("entry not found: %#v", id)}
	}
	logger.Info().Interface("entry", entry).Msg("registration entry found")
	entry.ManagedId = req.ManagedId
	if err := r.OmniSSM.Registrations.Update(ctx, entry); err != nil {
		return nil, err
	}
	logger.Info().Interface("entry", entry).Msg("registration entry updated")
	if t := r.OmniSSM.Config.ResourceRegisteredSNSTopic; t != "" {
		if data, err := json.Marshal(entry); err == nil {
			if err := r.OmniSSM.SNS.Publish(ctx, t, data); err != nil {
				logger.Error().Str("topic", t).Err(err).Msg("cannot send SNS message")
			}
		} else {
			logger.Error().Err(err).Msg("cannot marshal SNS message")
		}
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
				log.Error().Err(err).Msg("cannot unmarshal request body")
				return nil, lambda.BadRequestError{}
			}
			if err := registerReq.Verify(); err != nil {
				log.Error().Err(err).Msg("cannot verify request")
				return nil, lambda.BadRequestError{}
			}
			if a := registerReq.Identity().AccountId; !config.IsAuthorized(a) {
				return nil, lambda.UnauthorizedError{fmt.Sprintf("account not authorized: %#v", a)}
			}
			if !omni.RequestVersionValid(registerReq.ClientVersion) {
				return nil, lambda.BadRequestError{fmt.Sprintf("client version does not meet constraints %#v", omni.Config.ClientVersionConstraints)}
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
