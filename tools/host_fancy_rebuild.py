"""Rebuild and validate a fresh embedded-menu Fancy trial without installing it."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

from host_fancy import ROOT, digest, prepare_build_tools, snapshot_menus, stage
from host_fancy_trial import check_host_image, verify_files


def rebuild(args):
    if os.geteuid() == 0:
        raise ValueError('Run make host-fancy-rebuild as your regular user; compilation does not need root')
    if args.output is not None and args.output.exists():
        raise ValueError('Use a new output directory to preserve reviewed images and evidence')
    prepare_build_tools()
    subprocess.run(['sudo', '-v'], check=True)
    if args.output is None:
        directory = ROOT / 'build'
        directory.mkdir(exist_ok=True)
        workspace = Path(tempfile.mkdtemp(prefix='fancy-rebuild-', dir=directory))
    else:
        workspace = args.output.resolve()
        workspace.mkdir(parents=True, mode=0o700)
    print(f'Fancy rebuild: {workspace}', flush=True)
    snapshots = workspace / 'snapshot'
    snapshot_menus(snapshots)
    image = workspace / 'stage'
    stage(args.source, workspace / 'native', snapshots, image, args.pesign, args.module_source)
    manifest = json.loads((image / 'manifest.json').read_text())
    verify_files(image, manifest)
    check_host_image(manifest)
    evidence = workspace / 'evidence'
    print(f'Validating staged image in Secure Boot QEMU: {evidence}', flush=True)
    subprocess.run([sys.executable, str(ROOT / 'tools/host_fancy_vm.py'),
                    '--stage', str(image), '--output', str(evidence), '--original-timing'], check=True)
    # A kernel upgrade may finish while the VM checks are running. Do not offer
    # that image for installation if its embedded commands are already stale.
    current = workspace / 'current'
    snapshot_menus(current)
    for name, expected in manifest['snapshots'].items():
        if digest(current / name) != expected:
            raise ValueError('Host menu changed during validation. Run make host-fancy-rebuild again.')
    verify_files(image, manifest)
    setting = shlex.quote('HOST_FANCY_STAGE=' + str(image))
    print(f'Fancy rebuild passed. Inspect captures and logs in {evidence}.\n'
          'After review, remove an existing separate trial with make host-fancy-remove, then run:\n'
          f'make host-fancy-trial-install {setting}\n'
          'make host-fancy-enroll\n'
          'Host boot configuration unchanged.')
    return workspace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='new workspace; default: private build/fancy-rebuild-*')
    parser.add_argument('--source', type=Path, default=ROOT / 'build/host-fancy-source/grub2-unsigned-2.14')
    parser.add_argument('--pesign', default='pesign')
    parser.add_argument('--module-source', type=Path, default=ROOT / 'fancy/bourgeois.c')
    args = parser.parse_args()
    try:
        rebuild(args)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'bourgeois: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
