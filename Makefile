PYTHON ?= python3

.PHONY: vm vm-stop ssh screenshot test slim native-build fancy boot-test dist
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
	mkdir -p build
	$(CC) -std=c99 -Wall -Wextra -Werror fancy/state_test.c -o build/state-test
	build/state-test
slim:
	$(PYTHON) tools/preview.py slim
native-build:
	$(PYTHON) tools/native.py build
fancy:
	$(PYTHON) tools/preview.py fancy
	$(PYTHON) tools/native.py image
boot-test:
	$(PYTHON) -u tools/boot_test.py all
dist:
	$(PYTHON) tools/package.py
