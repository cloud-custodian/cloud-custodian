
install:
	python -m virtualenv --python python2.7 .
	. bin/activate && pip install -r requirements-dev.txt
	. bin/activate && pip install -e .

coverage:
	rm -Rf .coverage
	AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=foo AWS_SECRET_ACCESS_KEY=bar C7N_VALIDATE=true nosetests -s -v --with-coverage --cover-html --cover-package=c7n --cover-html-dir=coverage --processes=-1 --cover-inclusive tests  --process-timeout=64

test:
	./bin/tox -e py27

test3:
	./bin/tox -e py36

nose-tests:
	AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=foo AWS_SECRET_ACCESS_KEY=bar C7N_VALIDATE=true nosetests -s -v --processes=-1 --process-timeout=300 tests

ttest:
	AWS_DEFAULT_REGION=us-east-1 nosetests -s --with-timer --process-timeout=300 tests

depcache:
	mkdir -p deps
	python -m virtualenv --python python2.7 dep-download
	dep-download/bin/pip install -d deps -r requirements.txt
	tar cvf custodian-deps.tgz deps
	rm -Rf dep-download
	rm -Rf deps

ftest:
	C7N_FUNCTIONAL=yes AWS_DEFAULT_REGION=us-east-2 ./bin/py.test -m functional tests

sphinx:
	make -f docs/Makefile.sphinx clean && \
	make -f docs/Makefile.sphinx html

ghpages:
	-git checkout gh-pages && \
	mv docs/build/html new-docs && \
	rm -rf docs && \
	mv new-docs docs && \
	git add -u && \
	git add -A && \
	git commit -m "Updated generated Sphinx documentation"

lint:
	flake8 c7n tools/c7n_org tools/c7n_gcp tools/c7n_logexporter tools/c7n_mailer tools/c7n_sentry tools/c7n_sphinxext tools/zerodark tools/ops tools/c7n_azure

clean:
	rm -rf .tox .Python bin include lib pip-selfcheck.json

