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

package lambda

import (
	"encoding/json"
	"net/http"

	"github.com/aws/aws-lambda-go/events"
)

func Error(err error) (*events.APIGatewayProxyResponse, error) {
	code := http.StatusInternalServerError
	if gwErr, ok := err.(APIGatewayError); ok {
		code = gwErr.StatusCode()
	}
	return &events.APIGatewayProxyResponse{StatusCode: code, Body: err.Error()}, nil
}

func JSON(resp json.Marshaler, err error) (*events.APIGatewayProxyResponse, error) {
	if err != nil {
		return nil, err
	}
	data, err := json.Marshal(resp)
	if err != nil {
		return nil, err
	}
	return &events.APIGatewayProxyResponse{StatusCode: http.StatusOK, Body: string(data)}, nil
}
