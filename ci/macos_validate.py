"""AI-drafted acceptance of the exact distributed DMG, without account data or security overrides."""
import hashlib
import json
import os
import platform
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

EXPECTED_SHA256 = '1561dd83e1fec5a230b96dfa873ab847f514260eab2d9d83ed9e2373693f19d0'


def execute(arguments, *, timeout=90, env=None):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, env=env)
    if result.returncode:
        raise RuntimeError(f'{arguments[0]} exited {result.returncode}: {result.stderr[-3000:]}')
    return result.stdout


def validate(dmg, output, destination):
    output.mkdir(parents=True, exist_ok=True)
    result = {'status': 'failed', 'scope': 'exact v0.1.7 DMG runtime acceptance',
              'neo_hardware_tested': False, 'real_wechat_export_tested': False,
              'real_feishu_account_tested': False, 'download_quarantine_simulated': False,
              'machine': platform.machine(), 'macos': platform.mac_ver()[0],
              'github_sha': os.environ.get('GITHUB_SHA')}
    mounted = False
    try:
        assert sys.platform == 'darwin' and platform.machine() == 'arm64', 'Requires macOS arm64'
        result['installer_sha256'] = hashlib.sha256(dmg.read_bytes()).hexdigest()
        assert result['installer_sha256'] == EXPECTED_SHA256, 'Installer differs from distributed v0.1.7'
        result['disk_image'] = execute(['hdiutil', 'verify', str(dmg)])
        with tempfile.TemporaryDirectory(prefix='wechatemoji-ci-') as temporary:
            mount = Path(temporary) / 'mount'
            mount.mkdir()
            execute(['hdiutil', 'attach', '-readonly', '-nobrowse', '-noautoopen', '-mountpoint', str(mount), str(dmg)])
            mounted = True
            try:
                source = mount / '微信表情搬家.app'
                assert source.is_dir(), 'App missing from DMG'
                assert not destination.exists(), 'Refusing to replace an existing app'
                execute(['ditto', str(source), str(destination)])
            finally:
                execute(['hdiutil', 'detach', str(mount)])
                mounted = False
            execute(['codesign', '--verify', '--deep', '--strict', str(destination)])
            result['signature_integrity'] = 'passed_ad_hoc_only'
            assessment = subprocess.run(['spctl', '--assess', '--type', 'execute', '--verbose=4', str(destination)], capture_output=True, text=True)
            result['gatekeeper'] = {'exit_code': assessment.returncode,
                                    'message': assessment.stderr.strip(), 'apple_notarized': False}
            info = plistlib.loads((destination / 'Contents/Info.plist').read_bytes())
            result['version'] = info['CFBundleShortVersionString']
            assert result['version'] == '0.1.7'
            main = destination / 'Contents/MacOS' / info['CFBundleExecutable']
            assert os.access(main, os.X_OK), 'Main executable permission missing'
            result['architecture'] = execute(['lipo', '-archs', str(main)]).strip()
            assert 'arm64' in result['architecture'].split()
            helper = destination / 'Contents/Frameworks/runtime/wxemoticon'
            browser = next((destination / 'Contents/Resources/browser-runtime').glob('chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'))
            clean = {key: value for key, value in os.environ.items()
                     if key not in {'PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'PLAYWRIGHT_BROWSERS_PATH'} and not key.startswith('DYLD_')}
            clean['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
            result['helper_help'] = execute([str(helper), '--help'], env=clean)
            result['browser_version'] = execute([str(browser), '--version'], env=clean).strip()
            probe = Path(temporary) / 'launch-probe'
            execute(['xcrun', 'swiftc', str(Path(__file__).with_name('macos_launch.swift')), '-o', str(probe)], timeout=180)
            result['launch'] = json.loads(execute([str(probe), str(destination)], timeout=100, env=clean))
            assert result['launch']['status'] == 'passed'
            result['status'] = 'passed_runtime_only'
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        result['mount_cleanup_completed'] = not mounted
        (output / 'macos-runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    validate(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve())
