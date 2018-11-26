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

package ssm

import (
	"regexp"
	"strings"
)

// IsManagedInstance tests whether the provided EC2 instance identifier is
// managed.
func IsManagedInstance(s string) bool {
	return strings.HasPrefix(s, "mi-")
}

// original Java regexp for a valid tag: ^([\p{L}\p{Z}\p{N}_.:/=+\-@]*)$
var invalidTagRegexp = regexp.MustCompile(`[^a-zA-Z0-9\s_.:/=+\-@]`)

func SanitizeTag(t string) string {
	// special case of key: value# comment is this
	if i := strings.Index(t, "#"); i != -1 {
		t = t[:i]
	}
	t = strings.TrimSpace(t)
	return invalidTagRegexp.ReplaceAllString(t, "")
}
