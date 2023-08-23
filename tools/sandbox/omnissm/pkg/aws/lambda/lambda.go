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

// Package lambda provides helpers for interacting with AWS Lambda/API Gateway
package lambda

import (
	"context"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/rs/zerolog/log"
)

// Start wraps the provided handler function and returns the error message
// within the response. This allows for normal Go error handling to take place
// within the handler function while ensuring the error is contextualized
// within the API Gateway response.
func Start(fn func(context.Context, events.APIGatewayProxyRequest) (*events.APIGatewayProxyResponse, error)) {
	lambda.Start(func(ctx context.Context, req events.APIGatewayProxyRequest) (*events.APIGatewayProxyResponse, error) {
		resp, err := fn(ctx, req)
		if err != nil {
			log.Info().Msgf("received error from handler:\n%+v", err)
			return Error(err)
		}
		return resp, nil
	})
}
