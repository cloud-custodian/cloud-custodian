bucket=c7n-ssm-build

publish:
	GOOS=linux go build -o inventory-process process.go
	gzip inventory-process
	aws s3 cp --sse AES256 --acl public-read inventory-process.gz s3://$(bucket)/assets/inventory-process-linux-amd64.gz
	rm inventory-process.gz
