bucket=c7n-ssm-build

publish:
	GOOS=linux go build -o inventory-process process.go
	bzip2 inventory-process
	aws s3 cp --sse AES256 --acl public-read inventory-process.bz2 s3://$(bucket)/assets/inventory-process-linux-amd64.bz2
	rm inventory-process.bz2
