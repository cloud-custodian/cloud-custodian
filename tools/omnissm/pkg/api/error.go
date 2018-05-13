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
	"encoding/json"
	"net/http"

	"github.com/aws/aws-lambda-go/events"
	"github.com/pkg/errors"
)

type Error struct {
	Name    string `json:"error,omitempty"`
	Message string `json:"message,omitempty"`
}

func (e *Error) String() string {
	// it is safe to ignore the error here since we are passing only string
	// types to Marshal
	body, _ := json.Marshal(e)
	return string(body)
}

func (e *Error) Err() error {
	if e.Name != "" {
		return errors.New(e.Message)
	}
	return nil
}

func NewErrorResponse(status int, err error) *events.APIGatewayProxyResponse {
	e := &Error{
		Name:    http.StatusText(status),
		Message: err.Error(),
	}
	return &events.APIGatewayProxyResponse{
		StatusCode: status,
		Body:       e.String(),
	}
}
