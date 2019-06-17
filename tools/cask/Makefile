.PHONY: test
test:
	go test .

BINARY := cask
VERSION ?= vlatest

.PHONY: windows
windows:
	mkdir -p release
	GOOS=windows GOARCH=amd64 go build -o release/$(BINARY)-$(VERSION)-windows/custodian-cask.exe

.PHONY: linux
linux:
	mkdir -p release
	GOOS=linux GOARCH=amd64 go build -o release/$(BINARY)-$(VERSION)-linux-amd64/custodian-cask

.PHONY: darwin
darwin:
	mkdir -p release
	GOOS=darwin GOARCH=amd64 go build -o release/$(BINARY)-$(VERSION)-darwin-amd64/custodian-cask


.PHONY: release
release: windows linux darwin