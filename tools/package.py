"""Package local previews with source, notices, and SHA256 checksums."""
import hashlib
import gzip
from pathlib import Path
import shutil
import tarfile

import lab
import theme
from native import SOURCE_ARCHIVES


def stable_metadata(info):
    info.uid = info.gid = info.mtime = 0
    info.uname = info.gname = 'root'
    info.mode = 0o755 if info.isdir() else 0o644
    info.pax_headers = {}
    return info


def package():
    target = lab.BUILD / 'dist'
    target.mkdir(parents=True, exist_ok=True)
    for edition in ('slim', 'fancy'):
        stage = target / f'bourgeois-{edition}-preview'
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir()
        for name in ('LICENSE', 'README.adoc', 'Makefile', 'AGENTS.md', '.gitignore'):
            shutil.copyfile(lab.ROOT / name, stage / name)
        for name in ('assets', 'tools', 'docs'):
            shutil.copytree(lab.ROOT / name, stage / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        theme.build(stage / 'theme')
        for asset in ('courtyard.png', 'courtyard-nameplates.png', 'traveler.png'):
            shutil.copyfile(lab.ROOT / 'assets' / asset, stage / 'theme' / asset)
        # Both source archives carry the controller tests used by make test.
        shutil.copytree(lab.ROOT / 'fancy', stage / 'fancy')
        if edition == 'fancy':
            binary = lab.BUILD / 'native' / 'bourgeois.efi'
            if not binary.is_file():
                raise RuntimeError('Run make fancy before packaging')
            shutil.copyfile(binary, stage / 'bourgeois.efi')
            sources = stage / 'upstream-source'
            sources.mkdir()
            for name in SOURCE_ARCHIVES:
                cached = lab.BUILD / 'native' / 'upstream-source' / name
                if not cached.is_file():
                    raise RuntimeError('Run make native-build to cache the matching source archives')
                shutil.copyfile(cached, sources / name)
            (sources / 'BUILD.adoc').write_text('''= Corresponding source for the preview EFI image

The adjacent Ubuntu source archives contain GRUB 2.12-1ubuntu7.3 and Ubuntu's patches.
Extract them with `dpkg-source -x grub2-unsigned_2.12-1ubuntu7.3.dsc`.
The original module and controller are in `../fancy/` under GPLv3 or later.
The exact module registration, configure flags, compile command, dependency list, and EFI embedding command are in `../tools/native.py`.
The module compiles against the extracted Ubuntu tree.
The remaining modules and EFI kernel come from Ubuntu's matching `grub-efi-amd64-bin` package.
Build them from the supplied Ubuntu source with its Debian packaging, or use that exact Ubuntu package.
The bootstrap embeds the lab's /boot filesystem UUID, so the binary is tied to the development lab.
Rebuild the EFI image for another disk; do not install this binary on a real machine.
GRUB is GPLv3 or later; its full license is in `../fancy/LICENSE` and the upstream archives.
''')
        with (target / f'{stage.name}.tar.gz').open('wb') as stream:
            with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode='w') as archive:
                    archive.add(stage, arcname=stage.name, filter=stable_metadata)
    files = sorted(target.glob('*.tar.gz'))
    (target / 'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.name}\n' for file in files))
    print(target)


if __name__ == '__main__':
    package()
