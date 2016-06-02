
install:
	virtualenv .
	source bin/activate && pip install -r requirements.txt
	source bin/activate && python setup.py develop

develop:
	virtualenv .
	source bin/activate && pip install -r requirements-dev.txt
	source bin/activate && python setup.py develop

coverage:
	AWS_DEFAULT_REGION=us-east-1 ./bin/nosetests -s -v --with-coverage --cover-html --cover-package=c7n --cover-html-dir=cover --cover-inclusive tests

ttest:
	AWS_DEFAULT_REGION=us-east-1 ./bin/nosetests -s -v --with-timer tests
lint:
	flake8 c7n --ignore=W293,W291,W503,W391,E123

test:
	AWS_DEFAULT_REGION=us-east-1 ./bin/nosetests -s -v tests

ftests:
	AWS_DEFAULT_REGION=us-east-1 ./bin/nosetests -s -v ftests

depcache:
	mkdir -p deps
	virtualenv dep-download
	dep-download/bin/pip install -d deps -r requirements.txt
	tar cvf custodian-deps.tgz deps
	rm -Rf dep-download
	rm -Rf deps

sphinx:
	make -f docs/Makefile.sphinx clean && \
	make -f docs/Makefile.sphinx html

ghpages:
	git checkout gh-pages && \
	cp -r docs/build/html/* . && \
	git add -u && \
	git add -A && \
	git commit -m "Updated generated Sphinx documentation"
