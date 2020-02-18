.PHONY: test
test:
	go test .

BINARY := cask
VERSION ?= vlatest

.PHONY: windows
windows:
	mkdir -p release
	GOOS=windows GOARCH=amd64 go build -ldflags "-X main.version=$(VERSION)" -o release/windows-$(VERSION)/custodian-cask.exe

.PHONY: linux
linux:
	mkdir -p release
	GOOS=linux GOARCH=amd64 go build -ldflags "-X main.version=$(VERSION)" -o release/linux-$(VERSION)/custodian-cask

.PHONY: darwin
darwin:
	mkdir -p release
	GOOS=darwin GOARCH=amd64 go build -ldflags "-X main.version=$(VERSION)" -o release/darwin-$(VERSION)/custodian-cask


.PHONY: release
release: windows linux darwin