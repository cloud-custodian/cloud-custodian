bucket=c7n-ssm-build

publish:
	GOOS=linux go build -o ssm-initialize initialize.go
	gzip ssm-initialize
	aws s3 cp --sse AES256 --acl public-read ssm-initialize.gz s3://$(bucket)/assets/ssm-initialize-linux-amd64.gz
	rm ssm-initialize.gz
