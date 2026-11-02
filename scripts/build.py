#!/usr/bin/env python3
"""Build portable release files using only repository files and the stdlib."""

from pathlib import Path
import hashlib
import plistlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'


def build():
    info = plistlib.loads((ROOT / 'workflow/info.plist').read_bytes())
    assert info['bundleid'] == 'com.nando.eject-photo-library'
    assert info['name'] == 'Eject photo library'
    assert info['disabled'] is False
    DIST.mkdir(exist_ok=True)
    files = {
        'info.plist': (ROOT / 'workflow/info.plist', 0o644),
        'icon.png': (ROOT / 'assets/icon.png', 0o644),
        'eject-photo-library.zsh': (ROOT / 'src/eject-photo-library.zsh', 0o755),
        'alfred-launcher.zsh': (ROOT / 'workflow/alfred-launcher.zsh', 0o755),
        'alfred-list.zsh': (ROOT / 'workflow/alfred-list.zsh', 0o755),
        'README.md': (ROOT / 'README.md', 0o644),
        'LICENSE': (ROOT / 'LICENSE', 0o644),
    }
    archive = DIST / 'Eject.Photo.Library.alfredworkflow'
    with zipfile.ZipFile(archive, 'w') as bundle:
        for name, (source, mode) in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (0o100000 | mode) << 16
            bundle.writestr(entry, source.read_bytes())
    command = DIST / 'Eject.Photo.Library.command'
    command.write_bytes((ROOT / 'src/eject-photo-library.zsh').read_bytes())
    command.chmod(0o755)
    checksum = DIST / 'SHA256SUMS'
    checksum.write_text(''.join(
        f'{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.name}\n'
        for file in (archive, command)
    ))
    print(f'Built v{info["version"]}:')
    for file in (archive, command, checksum):
        print(f'  {file.relative_to(ROOT)}')


if __name__ == '__main__':
    build()
