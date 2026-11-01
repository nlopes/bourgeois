PYTHON ?= python3
HOST_SIZE ?= 2560x1440
HOST_STAGE ?= build/host-theme-review
BACKUP ?= /var/backups/bourgeois/latest
HOST_FANCY_STAGE ?= build/fancy-controller
HOST_FANCY_PESIGN ?= pesign
HOST_FANCY_MODULE_SOURCE ?= fancy/bourgeois.c
HOST_FANCY_EVIDENCE ?= build/fancy-sb-check
HOST_FANCY_DEMO ?= build/fancy-demo

.PHONY: vm vm-stop ssh screenshot test slim host-python host-preflight lab-preflight host-gpus host-gpu-select host-doctor host-stage host-install host-rollback native-build fancy boot-test dist
vm: lab-preflight
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
	$(CC) -std=c99 -Wall -Wextra -Werror fancy/layout_test.c -o build/layout-test
	build/layout-test
slim:
	$(PYTHON) tools/preview.py slim
host-python:
	@command -v "$(firstword $(PYTHON))" >/dev/null 2>&1 || { printf '%s\n' 'bourgeois: Python 3.11 or newer is required. Install python3 or set PYTHON to its path.' >&2; exit 1; }
	@$(PYTHON) -c 'import sys; sys.version_info >= (3, 11) or sys.exit("bourgeois: Python 3.11 or newer is required; set PYTHON to that interpreter.")'
host-preflight: host-python
	$(PYTHON) tools/host_checks.py all --sudo
lab-preflight: host-python
	$(PYTHON) tools/host_checks.py lab
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
.PHONY: host-fancy-stage host-fancy-check host-fancy-benchmark host-fancy-demo host-fancy-install host-fancy-enroll host-fancy-once host-fancy-remove
host-fancy-stage: host-python
	$(PYTHON) tools/host_fancy.py --output "$(HOST_FANCY_STAGE)" --pesign "$(HOST_FANCY_PESIGN)" --module-source "$(HOST_FANCY_MODULE_SOURCE)"
host-fancy-check: host-python
	$(PYTHON) tools/host_fancy_vm.py --stage "$(HOST_FANCY_STAGE)" --output "$(HOST_FANCY_EVIDENCE)"
host-fancy-benchmark: host-python
	$(PYTHON) tools/host_fancy_vm.py --stage "$(HOST_FANCY_STAGE)" --output "$(HOST_FANCY_EVIDENCE)" --original-timing
host-fancy-demo: host-python
	$(PYTHON) tools/host_fancy_vm.py --stage "$(HOST_FANCY_STAGE)" --output "$(HOST_FANCY_DEMO)" --record-demo
host-fancy-install: host-python
	sudo $(PYTHON) tools/host_fancy_trial.py install --stage "$(HOST_FANCY_STAGE)"
host-fancy-enroll: host-python
	sudo $(PYTHON) tools/host_fancy_trial.py enroll
host-fancy-once: host-python
	sudo $(PYTHON) tools/host_fancy_trial.py once
host-fancy-remove: host-python
	sudo $(PYTHON) tools/host_fancy_trial.py remove
native-build: lab-preflight
	$(PYTHON) tools/native.py build
fancy: lab-preflight
	$(PYTHON) tools/preview.py fancy
	$(PYTHON) tools/native.py image
boot-test:
	$(PYTHON) -u tools/boot_test.py all
dist:
	$(PYTHON) tools/package.py
