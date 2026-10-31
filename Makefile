PYTHON ?= python3

.PHONY: vm vm-stop ssh screenshot test
vm:
	$(PYTHON) tools/lab.py start
vm-stop:
	$(PYTHON) tools/lab.py stop
ssh:
	$(PYTHON) tools/lab.py ssh
screenshot:
	$(PYTHON) tools/lab.py screenshot
test:
	$(PYTHON) -m unittest discover -s tools -p '*_test.py' -v
