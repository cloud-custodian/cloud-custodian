/*
Copyright 2018 Capital One Services, LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.

You may obtain a copy of the License at
	http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package api

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/aws/aws-lambda-go/events"
	"github.com/pkg/errors"
	"github.com/rs/zerolog/log"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/identity"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/store"
)

type RegisterRequest struct {
	Provider  string          `json:"provider"`
	Document  json.RawMessage `json:"document"`
	Signature string          `json:"signature"`
	ManagedId string          `json:"managedId,omitempty"`

	document identity.Document
}

func (r *RegisterRequest) Identity() *identity.Document {
	return &r.document
}

func (r *RegisterRequest) Verify() error {
	if err := identity.Verify(r.Document, r.Signature); err != nil {
		return err
	}
	if err := json.Unmarshal(r.Document, &r.document); err != nil {
		return errors.Wrap(err, "cannot unmarshal identity document")
	}
	return nil
}

type RegisterResponse struct {
	*store.RegistrationEntry
	Error

	Region string `json:"region,omitempty"`
}

func (r *RouterContext) HandleCreateRegisterRequest(ctx context.Context, req *RegisterRequest) (*events.APIGatewayProxyResponse, error) {
	logger := log.With().Str("handler", "CreateRegistration").Logger()
	logger.Info().Interface("identity", req.Identity()).Msg("new registration request")
	entry, err, ok := r.Manager.Get(identity.Hash(req.Identity().Name()))
	if err != nil {
		return nil, err
	}
	if ok {
		entry, err = r.Manager.Register(req.Identity())
		if err != nil {
			return nil, errors.Wrapf(err, "unable to register: %#v", req.Identity().Name())
		}
		logger.Info().Interface("entry", entry).Msg("registration successful")
	} else {
		logger.Info().Interface("entry", entry).Msg("existing registration entry found")
	}
	logger.Info().Interface("entry", entry).Msg("registration entry found")
	data, err := json.Marshal(&RegisterResponse{
		RegistrationEntry: entry,
		Region:            req.Identity().Region,
	})
	if err != nil {
		return nil, err
	}
	logger.Info().Str("response", string(data)).Msg("new registration response")
	return &events.APIGatewayProxyResponse{StatusCode: http.StatusOK, Body: string(data)}, nil
}

func (r *RouterContext) HandleUpdateRegisterRequest(ctx context.Context, req *RegisterRequest) (*events.APIGatewayProxyResponse, error) {
	logger := log.With().Str("handler", "UpdateRegistration").Logger()
	logger.Info().Interface("identity", req.Identity()).Msg("update registration request")
	id := identity.Hash(req.Identity().Name())
	entry, err, ok := r.Manager.Get(id)
	if err != nil {
		return nil, err
	}
	if !ok {
		logger.Info().Str("instanceName", req.Identity().Name()).Str("id", id).Msg("registration entry not found")
		return nil, errors.Wrapf(err, "entry not found: %#v", id)
	}
	logger.Info().Interface("entry", entry).Msg("registration entry found")
	if req.ManagedId != "" {
		if err := r.Manager.Registrations.Update(entry); err != nil {
			return nil, errors.Wrapf(err, "unable to update entry: %#v", entry.Id)
		}
		logger.Info().Interface("entry", entry).Msg("registration entry updated")
	}
	data, err := json.Marshal(&RegisterResponse{RegistrationEntry: entry})
	if err != nil {
		return nil, err
	}
	logger.Info().Str("response", string(data)).Msg("update registration response")
	return &events.APIGatewayProxyResponse{StatusCode: http.StatusOK, Body: string(data)}, nil
}
