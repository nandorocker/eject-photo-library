from pathlib import Path
import copy
import json
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/eject-photo-library.zsh').read_text()
PHOTO = '/System/Library/PrivateFrameworks/PhotoLibraryServices.framework/Versions/A/Support/photolibraryd'
MEDIA = '/System/Library/PrivateFrameworks/MediaAnalysis.framework/Versions/A/mediaanalysisd'

FAKE = r'''
from pathlib import Path
import json, os, plistlib, sys
p = Path(os.environ['EJECT_TEST_STATE'])
s = json.loads(p.read_text())
cmd = Path(sys.argv[0]).name
args = sys.argv[1:]
s['calls'].append([cmd, *args])
rc = 0
if cmd == 'hdiutil':
    if s.get('bad_plist'):
        print('not a plist')
    else:
        images = []
        for im in s['images']:
            if im.get('attached', True):
                images.append({'image-path': im['path'], 'system-entities': [
                    {'dev-entry': im['device']},
                    {'dev-entry': im['device'] + 's1', 'mount-point': im['mount']}
                ]})
        sys.stdout.buffer.write(plistlib.dumps({'images': images}))
elif cmd == 'diskutil':
    assert args[0] == 'eject' and len(args) == 2, args
    im = next(im for im in s['images'] if im['device'] == args[1] and im.get('attached', True))
    killed = s.get('killed', [])
    if im.get('always_busy') or (im.get('busy') and not all(b['pid'] in killed for b in im['blockers'])):
        print('Resource busy')
        rc = 1
    else:
        im['attached'] = False
        print('Disk ejected')
elif cmd == 'lsof':
    requested_mounts = args[args.index('--') + 1:]
    im = next(im for im in s['images'] if im['mount'] in requested_mounts)
    if im.get('lsof_error'):
        print('inspection denied', file=sys.stderr)
        rc = 1
    elif im.get('blockers'):
        for b in im['blockers']:
            print('p' + str(b['pid']))
            print('c' + b['name'])
            for file in b.get('files', []):
                print('n' + im['mount'] + '/' + file)
    else:
        rc = 1
elif cmd == 'ps':
    b = next(b for im in s['images'] for b in im.get('blockers', []) if b['pid'] == int(args[1]))
    print(b.get('uid', os.getuid()) if args[3] == 'uid=' else b['executable'])
elif cmd == 'kill':
    assert args[0] == '-TERM' and len(args) == 2 and int(args[1]) > 1, args
    s.setdefault('killed', []).append(int(args[1]))
elif cmd != 'sleep':
    raise AssertionError(cmd)
p.write_text(json.dumps(s))
sys.exit(rc)
'''

KNOWN = [
    {'pid': 12345, 'name': 'photolibraryd', 'executable': PHOTO, 'files': ['Library.photoslibrary/database/Photos.sqlite']},
    {'pid': 12346, 'name': 'mediaanalysisd', 'executable': MEDIA, 'files': ['Library.photoslibrary/resources/a']},
]
def image(path='/Users/test/Pictures/Arbitrary.sparsebundle', device='/dev/disk42', mount='/Volumes/Confidential Label', **extra):
    return {'path': path, 'device': device, 'mount': mount, 'blockers': copy.deepcopy(KNOWN), **extra}

def run(label, images, args=(), rc=0, ejects=0, kills=0, check=None, **extra):
    with tempfile.TemporaryDirectory(prefix='generic-eject-test-') as td:
        base = Path(td)
        script = SOURCE
        for command in ['/usr/bin/hdiutil', '/usr/sbin/diskutil', '/usr/sbin/lsof', '/bin/ps', '/bin/kill', '/bin/sleep']:
            stub = base / Path(command).name
            stub.write_text(f'#!{sys.executable}\n' + FAKE)
            stub.chmod(0o755)
            script = script.replace(command, str(stub))
        executable = base / 'eject.zsh'
        executable.write_text(script)
        state_path = base / 'state.json'
        state_path.write_text(json.dumps({'images': images, 'calls': [], **extra}))
        result = subprocess.run(['/bin/zsh', str(executable), '--no-pause', *args],
            env={**os.environ, 'EJECT_TEST_STATE': str(state_path)}, text=True, capture_output=True, timeout=30)
        state = json.loads(state_path.read_text())
        assert result.returncode == rc, (label, result.returncode, result.stdout, result.stderr)
        assert len([c for c in state['calls'] if c[0]=='diskutil']) == ejects, (label, state, result.stdout)
        assert len([c for c in state['calls'] if c[0]=='kill']) == kills, (label, state, result.stdout)
        assert all('-force' not in c and '-9' not in c for c in state['calls'])
        if rc:
            assert 'safely ejected' not in result.stdout
        if check:
            check(result, state)
        print('PASS:', label)

def rows(result):
    return json.loads(result.stdout)['items']

run('empty list produces an inactive result', [], ['--list'], check=lambda r,s: rows(r)[0]['valid'] is False or sys.exit(1))
run('single result hides image and library names', [image()], ['--list'],
    check=lambda r,s: (rows(r)[0]['title']=='Eject photo library' and 'Confidential' not in rows(r)[0]['subtitle'] and rows(r)[0]['arg']==s['images'][0]['path']) or sys.exit(1))
run('arbitrarily named image is discovered and ejected', [image()], ejects=1)
run('known background helpers are gracefully released', [image(busy=True)], ejects=2, kills=2)
run('unrelated files open in Photos services do not qualify', [image(blockers=[{**KNOWN[0], 'files':['other.sqlite']}])], ['--list'],
    check=lambda r,s: rows(r)[0]['valid'] is False or sys.exit(1))
run('similar extension does not qualify', [image(blockers=[{**KNOWN[0], 'files':['Library.photoslibrary-old/db']}])], ['--list'],
    check=lambda r,s: rows(r)[0]['valid'] is False or sys.exit(1))
run('library extension matching is case insensitive', [image(blockers=[{**KNOWN[0], 'files':['Library.PHOTOSLIBRARY/db']}])], ['--list'],
    check=lambda r,s: rows(r)[0]['valid'] is True or sys.exit(1))
second=image(path='/Users/test/Other.dmg', device='/dev/disk99', mount='/Volumes/Other library')
run('several images are offered individually', [image(), second], ['--list'],
    check=lambda r,s: len(rows(r))==2 and rows(r)[1]['arg']==second['path'] or sys.exit(1))
run('automatic mode refuses to pick among several images', [image(), second], rc=1)
run('selected image alone is ejected', [image(), second], ['--image', second['path']], ejects=1,
    check=lambda r,s: s['images'][0].get('attached',True) and not s['images'][1]['attached'] or sys.exit(1))
photos={'pid':12347,'name':'Photos','executable':'/System/Applications/Photos.app/Contents/MacOS/Photos','files':['Library.photoslibrary/db']}
run('Photos app is offered but must be closed manually', [image(blockers=KNOWN+[photos], busy=True)], rc=1, ejects=1)
run('other account service is not signaled', [image(blockers=[{**KNOWN[0],'uid':0}], busy=True)], rc=1, ejects=1)
run('impostor helper executable is not signaled', [image(blockers=[{**KNOWN[0],'executable':'/tmp/photolibraryd'}], busy=True)], rc=1, ejects=1)
run('unknown app alone does not make a candidate', [image(blockers=[{**photos,'name':'Backup'}])], ['--list'],
    check=lambda r,s: rows(r)[0]['valid'] is False or sys.exit(1))
run('inspection failure prevents selection and signals', [image(lsof_error=True)], ['--list'], rc=1)
run('retries stop after three graceful releases', [image(always_busy=True)], ejects=4, kills=6, rc=1)
run('selected image already detached is harmless', [], ['--image', '/Users/test/No longer mounted.dmg'])
run('duplicate source mapping is refused', [image(), image(device='/dev/disk99')], ['--image', image()['path']], rc=1)
run('invalid image metadata is refused', [image()], ['--list'], rc=1, bad_plist=True)
special='/Users/test/Café "quoted" \\ tab\tline\n.sparsebundle'
run('JSON safely carries unusual path characters', [image(path=special)], ['--list'],
    check=lambda r,s: rows(r)[0]['arg']==special or sys.exit(1))
