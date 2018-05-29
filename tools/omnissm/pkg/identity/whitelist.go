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

package identity

import (
	"strings"

	"github.com/pkg/errors"
)

var ErrUnauthorizedAccount = errors.New("unauthorized account")

// A Whitelist stores a map of account values for existential lookups.
type Whitelist struct {
	accounts map[string]struct{}
}

// NewWhitelist returns a new whitelist for authorized accounts.
func NewWhitelist(s string) *Whitelist {
	w := &Whitelist{
		accounts: make(map[string]struct{}),
	}
	for _, acctId := range strings.Split(s, ",") {
		w.accounts[acctId] = struct{}{}
	}
	return w
}

func (w *Whitelist) Exists(acct string) (ok bool) {
	if acct == "" {
		return
	}
	_, ok = w.accounts[acct]
	return
}
