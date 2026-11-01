PYTHON ?= python3
HOST_SIZE ?= 2560x1440
HOST_STAGE ?= build/host-theme-review
BACKUP ?= /var/backups/bourgeois/latest

.PHONY: vm vm-stop ssh screenshot test slim host-python host-preflight host-gpus host-gpu-select host-doctor host-stage host-install host-rollback native-build fancy boot-test dist
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
host-python:
	@command -v "$(firstword $(PYTHON))" >/dev/null 2>&1 || { printf '%s\n' 'bourgeois: Python 3.11 or newer is required. Install python3 or set PYTHON to its path.' >&2; exit 1; }
	@$(PYTHON) -c 'import sys; sys.version_info >= (3, 11) or sys.exit("bourgeois: Python 3.11 or newer is required; set PYTHON to that interpreter.")'
host-preflight: host-python
	$(PYTHON) tools/host_checks.py all --sudo
host-gpus: host-python
	$(PYTHON) tools/host_gpu.py $(if $(GPU),--gpu "$(GPU)")
host-gpu-select: host-python
	$(PYTHON) tools/host_gpu.py --select
host-doctor: host-preflight host-gpus
host-stage: host-python
	$(PYTHON) tools/host_theme.py "$(HOST_STAGE)" --size "$(HOST_SIZE)"
host-install: host-preflight host-stage
	sudo $(PYTHON) tools/host_install.py install --stage "$(HOST_STAGE)"
host-rollback: host-python
	$(PYTHON) tools/host_checks.py install --sudo
	sudo $(PYTHON) tools/host_install.py rollback --backup "$(BACKUP)"
native-build:
	$(PYTHON) tools/native.py build
fancy:
	$(PYTHON) tools/preview.py fancy
	$(PYTHON) tools/native.py image
boot-test:
	$(PYTHON) -u tools/boot_test.py all
dist:
	$(PYTHON) tools/package.py
