"""Disposable Ubuntu UEFI lab. No host boot configuration is modified."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
VM = BUILD / "vm"
CACHE = BUILD / "cache"
PORT = int(os.environ.get("BOURGEOIS_SSH_PORT", "2229"))
IMAGE = "noble-server-cloudimg-amd64.img"


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


class QMP:
    def __init__(self):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.settimeout(10)
        self.socket.connect(str(VM / "qmp.sock"))
        self.stream = self.socket.makefile("rwb", buffering=0)
        self.read()
        self.command("qmp_capabilities")

    def read(self):
        line = self.stream.readline()
        if not line:
            raise ConnectionError("QEMU closed its monitor")
        return json.loads(line)

    def command(self, name, arguments=None):
        request = {"execute": name}
        if arguments is not None:
            request["arguments"] = arguments
        self.stream.write(json.dumps(request).encode() + b"\n")
        while True:
            response = self.read()
            if "error" in response:
                raise RuntimeError(response["error"])
            if "return" in response:
                return response["return"]

    def close(self):
        self.stream.close()
        self.socket.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def download_image():
    CACHE.mkdir(parents=True, exist_ok=True)
    image = CACHE / IMAGE
    lock = json.loads((ROOT / "tools" / "ubuntu-image.json").read_text())
    if not image.exists():
        part = image.with_suffix(".img.part")
        print("Downloading Ubuntu 24.04 amd64 image", flush=True)
        with urllib.request.urlopen(lock["url"], timeout=60) as response, part.open("wb") as output:
            shutil.copyfileobj(response, output)
        verify_digest(part, lock["sha256"])
        part.rename(image)
    verify_digest(image, lock["sha256"])
    (CACHE / "image.json").write_text(json.dumps(lock, indent=2) + "\n")
    return image


def verify_digest(path, expected):
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise RuntimeError(f"Image checksum mismatch: {actual}; expected {expected}")


def firmware():
    explicit = os.environ.get("BOURGEOIS_FIRMWARE")
    candidates = [Path(explicit)] if explicit else []
    candidates += [Path("/opt/homebrew/share/qemu/edk2-x86_64-code.fd"),
                   Path("/usr/share/OVMF/OVMF_CODE.fd"),
                   Path("/usr/share/OVMF/OVMF_CODE_4M.fd"),
                   Path("/usr/share/edk2/ovmf/OVMF_CODE.fd")]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("UEFI firmware missing; install QEMU/OVMF or set BOURGEOIS_FIRMWARE")


def prepare():
    VM.mkdir(parents=True, exist_ok=True)
    image = download_image()
    if not (VM / "id_ed25519").exists():
        run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", VM / "id_ed25519")
    if not (VM / "disk.qcow2").exists():
        run("qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", image, VM / "disk.qcow2", "24G")
    key = (VM / "id_ed25519.pub").read_text().strip()
    (VM / "user-data").write_text(f"""#cloud-config
users:
  - name: bourgeois
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - {key}
ssh_pwauth: false
write_files:
  - path: /etc/systemd/system/bourgeois-marker.service
    content: |
      [Unit]
      Description=bourgeois Linux boot marker
      After=network.target
      [Service]
      Type=oneshot
      ExecStart=/bin/sh -c 'echo BOURGEOIS_LINUX_OK > /dev/ttyS0'
      [Install]
      WantedBy=multi-user.target
runcmd:
  - [systemctl, enable, --now, bourgeois-marker.service]
""")
    (VM / "meta-data").write_text("instance-id: bourgeois-lab-v1\nlocal-hostname: bourgeois-lab\n")
    run("xorriso", "-as", "mkisofs", "-quiet", "-o", VM / "seed.iso", "-V", "cidata", "-J", "-r",
        VM / "user-data", VM / "meta-data", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start():
    try:
        with QMP() as monitor:
            print(f"QEMU already running: {monitor.command('query-status')['status']}")
        return
    except (OSError, ConnectionError):
        pass
    prepare()
    accel = "kvm" if platform.system() == "Linux" and os.access("/dev/kvm", os.R_OK | os.W_OK) else "tcg,thread=multi"
    code = firmware()
    variables = VM / "uefi-vars.fd"
    if not variables.exists():
        candidates = [code.parent / "edk2-i386-vars.fd", code.parent / "OVMF_VARS.fd",
                      code.parent / "OVMF_VARS_4M.fd"]
        template = next((path for path in candidates if path.is_file()), None)
        if template is None:
            raise RuntimeError("UEFI variables template not found beside firmware")
        shutil.copyfile(template, variables)
    args = ["qemu-system-x86_64", "-machine", "q35", "-accel", accel, "-cpu", "max",
            "-m", "4096", "-smp", "2",
            "-drive", f"if=pflash,format=raw,readonly=on,file={code}",
            "-drive", f"if=pflash,format=raw,file={variables}",
            "-drive", f"file={VM / 'disk.qcow2'},if=virtio,format=qcow2",
            "-drive", f"file={VM / 'seed.iso'},media=cdrom,readonly=on",
            "-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{PORT}-:22",
            "-device", "virtio-net-pci,netdev=net0", "-display", "none", "-vga", "std",
            "-serial", f"file:{VM / 'serial.log'}", "-debugcon", f"file:{VM / 'debug.log'}",
            "-qmp", f"unix:{VM / 'qmp.sock'},server=on,wait=off"]
    (VM / "qmp.sock").unlink(missing_ok=True)
    with (VM / "qemu.log").open("ab") as log:
        process = subprocess.Popen(args, stdout=log, stderr=log, start_new_session=True)
    (VM / "pid").write_text(str(process.pid) + "\n")
    (VM / "launch.json").write_text(json.dumps(args, indent=2) + "\n")
    time.sleep(0.3)
    if process.poll() is not None:
        raise RuntimeError(f"QEMU exited with {process.returncode}; inspect {VM / 'qemu.log'}")
    print(f"QEMU started (PID {process.pid}); SSH localhost:{PORT}. Logs: {VM}")


def ssh_args():
    return ["ssh", "-i", str(VM / "id_ed25519"), "-p", str(PORT),
            "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={VM / 'known_hosts'}",
            "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", "bourgeois@127.0.0.1"]


def ssh(command=None, **kwargs):
    return run(*ssh_args(), *([command] if command else []), **kwargs)


def wait_ssh(timeout=900):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(ssh_args() + ["true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            return
        time.sleep(3)
    raise TimeoutError(f"Guest SSH did not start; inspect {VM / 'serial.log'}")


def screenshot(path=None):
    target = Path(path) if path else BUILD / "evidence" / "screen.png"
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with QMP() as monitor:
        monitor.command("screendump", {"filename": str(target), "format": "png"})
    print(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "stop", "ssh", "wait", "screenshot"])
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    if args.command == "start":
        start()
    elif args.command == "stop":
        with QMP() as monitor:
            monitor.command("quit")
    elif args.command == "wait":
        wait_ssh()
    elif args.command == "ssh":
        ssh(args.argument)
    elif args.command == "screenshot":
        screenshot(args.argument)


if __name__ == "__main__":
    main()
