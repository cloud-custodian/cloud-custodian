.PHONY: test
test:
	go test .

BINARY := mytool
VERSION ?= vlatest

.PHONY: windows
windows:
	mkdir -p release
	GOOS=windows GOARCH=amd64 go build -o release/$(BINARY)-$(VERSION)-windows/custodian-cask.exe

.PHONY: linux
linux:
	mkdir -p release
	GOOS=linux GOARCH=amd64 go build -o release/$(BINARY)-$(VERSION)-$(os)-amd64/custodian-cask

.PHONY: darwin
darwin:
	mkdir -p release
	GOOS=darwin GOARCH=amd64 go build -o release/$(BINARY)-$(VERSION)-$(os)-amd64/custodian-cask


.PHONY: release
release: windows linux darwin