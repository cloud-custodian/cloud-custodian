bucket=c7n-ssm-build

publish:
	GOOS=linux go build -o ssm-initialize initialize.go
	bzip2 ssm-initialize
	aws s3 cp --sse AES256 --acl public-read ssm-initialize.bz2 s3://$(bucket)/assets/ssm-initialize-linux-amd64.bz2
	rm ssm-initialize.bz2
