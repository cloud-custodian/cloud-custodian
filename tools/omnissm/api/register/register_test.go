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
package main

import (
	"encoding/json"
	"testing"
)

func TestValidateRequest(t *testing.T) {
	type errorResponse struct {
		Error   string `json:"error"`
		Message string `json:"message"`
	}

	failureCases := []struct {
		name string
		body string
		err  errorResponse
	}{
		{
			name: "empty request",
			body: "",
			err:  errorResponse{"invalid-request", "malformed json"},
		},
		{
			name: "malformed json",
			body: "{",
			err:  errorResponse{"invalid-request", "malformed json"},
		},
		{
			name: "unknown provider",
			body: `{"identity":"","signature":"","provider":"unknown","managed-id":""}`,
			err:  errorResponse{"invalid-request", "unknown provider"},
		},
		{
			name: "signature not base64",
			body: `{"identity":"identity","signature":"not%%base64","provider":"aws","managed-id":""}`,
			err:  errorResponse{"invalid-request", "malformed rsa signature"},
		},
		{
			name: "signature blank",
			body: `{"identity":"identity","signature":"","provider":"aws","managed-id":""}`,
			err:  errorResponse{"invalid-signature", "invalid identity"},
		},
		{
			name: "signature not valid",
			body: `{"identity":"identity","signature":"aWRlbnRpdHkK","provider":"aws","managed-id":""}`,
			err:  errorResponse{"invalid-signature", "invalid identity"},
		},
	}

	for _, c := range failureCases {
		t.Run(c.name, func(t *testing.T) {
			_, resp := validateRequest(c.body)
			if resp.StatusCode != 400 {
				t.Errorf("response status code was %d, expected 400", resp.StatusCode)
			}
			var errResp errorResponse
			if err := json.Unmarshal([]byte(resp.Body), &errResp); err != nil {
				t.Errorf("error unmarshaling reponse body: %v", err)
			}
			if errResp != c.err {
				t.Errorf("\n\texpected '%+v'\n\tgot      '%+v'", c.err, errResp)
			}
		})
	}
}
