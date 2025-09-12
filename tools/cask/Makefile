.PHONY: test
test:
	go test .

BINARY := cask
VERSION ?= latest

.PHONY: windows
windows:
	mkdir -p release
	GOOS=windows GOARCH=amd64 go build -ldflags "-X main.version=$(VERSION)" -o release/windows-$(VERSION)/custodian-cask.exe

.PHONY: linux
linux:
	mkdir -p release
	GOOS=linux GOARCH=amd64 go build -ldflags "-X main.version=$(VERSION)" -o release/linux-$(VERSION)/custodian-cask

.PHONY: linux-arm
linux-arm:
	mkdir -p release
	GOOS=linux GOARCH=arm64 go build -ldflags "-X main.version=$(VERSION)" -o release/linux-arm64-$(VERSION)/custodian-cask

.PHONY: darwin
darwin:
	mkdir -p release
	GOOS=darwin GOARCH=amd64 go build -ldflags "-X main.version=$(VERSION)" -o release/darwin-$(VERSION)/custodian-cask


.PHONY: darwin-arm
darwin-arm:
	mkdir -p release
	GOOS=darwin GOARCH=arm64 go build -ldflags "-X main.version=$(VERSION)" -o release/darwin-arm64-$(VERSION)/custodian-cask


.PHONY: release
release: windows linux linux-arm darwin darwin-arm
