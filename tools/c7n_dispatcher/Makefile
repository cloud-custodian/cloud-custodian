install:
	python -m virtualenv --python python2.7 .
	. bin/activate && pip install -r requirements.txt
	. bin/activate && python setup.py develop

clean:
	rm -rf .tox .Python bin include lib pip-selfcheck.json

	