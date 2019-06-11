bucket=c7n-ssm-build
stack-name=omnissm-functions
functions := $(wildcard */.)

deploy:
	aws cloudformation package --template-file cfn.yaml --s3-bucket $(bucket) --s3-prefix builds --output-template built-template.yaml
	aws cloudformation deploy --template-file built-template.yaml --stack-name $(stack-name)
	$(MAKE) clean

delete:
	aws cloudformation delete-stack --stack-name=$(stack-name)

update: $(functions)
$(functions):
	cd $@ && $(MAKE) update

clean:
	@rm -f built-template.yaml

.PHONY: $(functions)
