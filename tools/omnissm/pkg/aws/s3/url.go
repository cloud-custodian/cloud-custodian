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

package s3

import (
	"fmt"
	"net/url"
	"regexp"
	"strings"

	"github.com/pkg/errors"
)

var IsAlphaNumeric = regexp.MustCompile(`^[a-zA-Z0-9\.-]+$`).MatchString

type URL struct {
	Bucket, Path string
}

func ParseURL(s string) (*URL, error) {
	if !strings.HasPrefix(s, "s3://") {
		s = fmt.Sprintf("s3://%s", s)
	}
	url, err := url.Parse(s)
	if err != nil {
		return nil, err
	}
	if strings.ToLower(url.Scheme) != "s3" {
		return nil, errors.Errorf("scheme: received %#v, expected \"s3\"", url.Scheme)
	}
	if !IsAlphaNumeric(url.Host) {
		return nil, errors.Errorf("s3 url invalid host: %#v", url.Host)
	}
	u := &URL{
		Bucket: url.Host,
		Path:   strings.TrimLeft(url.Path, "/"),
	}
	return u, nil
}

func (u *URL) String() string {
	return fmt.Sprintf("s3://%s/%s", u.Bucket, u.Path)
}
