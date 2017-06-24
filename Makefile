
install:
	python -m virtualenv --python python2.7 .
	. bin/activate && pip install -r requirements.txt
	. bin/activate && python setup.py develop

coverage:
	rm -Rf .coverage
	AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=foo AWS_SECRET_ACCESS_KEY=bar C7N_VALIDATE=true nosetests -s -v --with-coverage --cover-html --cover-package=c7n --cover-html-dir=coverage --processes=-1 --cover-inclusive tests  --process-timeout=64

ttest:
	AWS_DEFAULT_REGION=us-east-1 nosetests -s --with-timer --process-timeout=300 tests

depcache:
	mkdir -p deps
	python -m virtualenv --python python2.7 dep-download
	dep-download/bin/pip install -d deps -r requirements.txt
	tar cvf custodian-deps.tgz deps
	rm -Rf dep-download
	rm -Rf deps

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

clean:
	rm -rf .tox .Python bin include lib pip-selfcheck.json
