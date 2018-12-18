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

import "net/http"

type APIGatewayError interface {
	StatusCode() int
}

type BadRequestError struct {
	Message string
}

func (e BadRequestError) Error() string {
	if e.Message == "" {
		return "bad request"
	}
	return e.Message
}
func (BadRequestError) StatusCode() int { return http.StatusBadRequest }

type NotFoundError struct {
	Message string
}

func (e NotFoundError) Error() string {
	return e.Message
}
func (NotFoundError) StatusCode() int { return http.StatusNotFound }

type UnauthorizedError struct {
	Message string
}

func (e UnauthorizedError) Error() string {
	return e.Message
}
func (UnauthorizedError) StatusCode() int { return http.StatusUnauthorized }
