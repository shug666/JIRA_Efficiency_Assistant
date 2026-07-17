#!/usr/bin/env python3
"""JIRA 效率助手 — 一键打包发版脚本（Chrome + Firefox 双版本）
============================================================

在 master 分支（开发仓库）执行，自动完成：
  1. 改 Chrome/Firefox manifest + package.json 版本号
  2. npm run build（两端）
  3. Chrome: source.pem 打包 crx
  4. Firefox: web-ext 打包/签名 xpi
  5. 生成 update.xml / updates.json
  6. 自动同步产物到 release-main 分支 → 推送到 GitHub Pages 仓库

用法
----
  # 每次发版前必须先激活虚拟环境
  source .venv/bin/activate

  python3 scripts/release.py 3.5.0                      # 全流程：版本号+编译+打包+推送
  python3 scripts/release.py 3.5.0 --chrome             # 只 Chrome（无需任何密钥）
  python3 scripts/release.py 3.5.0 --firefox --sign     # 只 Firefox 签名版（需 AMO 密钥）
  python3 scripts/release.py 3.5.0 --sign               # Chrome + Firefox 签名版
  python3 scripts/release.py 3.5.0 --build-only         # 只更新版本号 + npm build（不打包不推送）
  python3 scripts/release.py 3.5.0 --release-only       # 只更新版本号 + 生成清单 + 推送（跳过编译和打包）
  python3 scripts/release.py 3.5.0 --no-build           # 跳过 npm run build
  python3 scripts/release.py 3.5.0 --no-pack            # 跳过打包（手动签名后用已有 crx/xpi）
  python3 scripts/release.py 3.5.0 --no-push            # 只打包不推送（检查产物）

参数说明
--------
  version             新版本号 X.Y.Z（每次发版必须递增，AMO 不允许同版本号重复签名）
  --chrome            只打包 Chrome
  --firefox           只打包 Firefox
  --sign              Firefox 签名（需 AMO 密钥）
  --build-only        只更新版本号 + npm build（不打包不推送，适合改完代码先编译验证）
  --release-only      只更新版本号 + 生成清单 + 推送（跳过编译和打包，手动签名后用）
  --no-build          跳过 npm run build
  --no-pack           跳过打包（手动签名文件放到 _dist_release/releases/ 后用此参数）
  --no-push           只打包不推送到 GitHub（检查产物用）

前置条件
--------
  - 在 master 分支执行（有 input/source、output/firefox、source.pem）
  - 激活虚拟环境: source .venv/bin/activate（cryptography 库需要）
  - 首次需安装: pip install cryptography -i https://mirrors.aliyun.com/pypi/simple/
  - Firefox 签名: AMO 密钥配置在 ~/.zshrc（AMO_JWT_ISSUER / AMO_JWT_SECRET）
  - Firefox 签名需等待 AMO 审核，可能数分钟到数小时

自动完成的工作
--------------
  1. 改版本号（Chrome/Firefox manifest + package.json）
  2. npm run build（Vue SPA 编译）
  3. Chrome: 纯 Python crx3 打包（source.pem 签名）
  4. Firefox: web-ext 打包/签名 xpi
  5. 生成 update.xml / updates.json
  6. 更新首页 HTML 版本号显示
  7. 同步产物到 release-main 分支 → 推送到 GitHub Pages
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name == 'scripts' else Path.cwd()
if not (ROOT / 'input' / 'source').exists():
    ROOT = Path.cwd()

# 源码（master 分支有）
CHROME_SOURCE_DIR = ROOT / 'input' / 'source'
CHROME_MANIFEST = CHROME_SOURCE_DIR / 'manifest.json'
PEM_FILE = ROOT / 'input' / 'source.pem'
FIREFOX_SOURCE_DIR = ROOT / 'output' / 'firefox'
FIREFOX_MANIFEST = FIREFOX_SOURCE_DIR / 'manifest.json'
PACKAGE_JSON = CHROME_SOURCE_DIR / 'package.json'

# 本地产物输出（临时目录，不提交到 master）
DIST_DIR = ROOT / '_dist_release'
RELEASES_DIR = DIST_DIR / 'releases'
CHROME_UPDATE_XML = DIST_DIR / 'update.xml'
FIREFOX_UPDATES_JSON = DIST_DIR / 'updates.json'

# release-main 分支相关
RELEASE_BRANCH = 'release-main'
RELEASE_REMOTE = 'release'

# 常量
GITHUB_PAGES_BASE = 'https://shug666.github.io/JIRA_Efficiency_Assistant'
CHROME_EXT_ID = 'inmachhhbcehlpklfjgenplmgffbiiaf'
FIREFOX_EXT_ID = 'jira-template-manager@shugan'
FIREFOX_MIN_VERSION = '128.0'
EXT_NAME = 'jira-helper'


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def log(msg: str) -> None:
    print(f'[release] {msg}')


def fail(msg: str, code: int = 1) -> None:
    print(f'[release][错误] {msg}', file=sys.stderr)
    sys.exit(code)


def run(cmd: list[str] | str, cwd: Path | None = None, check: bool = True, env: dict | None = None, timeout: int | None = None) -> subprocess.CompletedProcess:
    log(f'$ {cmd if isinstance(cmd, str) else " ".join(cmd)}')
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=check, env=env, text=True, capture_output=True, timeout=timeout)
    if result.stdout and result.stdout.strip():
        print(result.stdout.rstrip()[:800])
    if result.stderr and result.stderr.strip():
        # web-ext 等工具的错误信息在 stderr，打印出来方便排查
        print(result.stderr.rstrip()[:800], file=sys.stderr)
    return result


def find_chrome() -> str:
    candidates = [
        'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser',
        '/opt/google/chrome/chrome', '/usr/bin/google-chrome',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        r'C:Program Files\Google\Chrome\Application\chrome.exe',
        r'C:Program Files (x86)\Google\Chrome\Application\chrome.exe',
    ]
    for c in candidates:
        if shutil.which(c) or os.path.exists(c):
            return c
    fail('未找到 Chrome / Chromium。请安装，或手动在 chrome://extensions 打包后用 --no-pack。')


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    import base64
    return 'sha256:' + base64.b64encode(h.digest()).decode()


# ---------------------------------------------------------------------------
# 版本号管理
# ---------------------------------------------------------------------------
def bump_version(new_version: str, targets: list[str]) -> None:
    if not re.fullmatch(r'\d+\.\d+\.\d+', new_version):
        fail(f'版本号格式应为 X.Y.Z，收到: {new_version}')

    if 'chrome' in targets and CHROME_MANIFEST.exists():
        data = json.loads(CHROME_MANIFEST.read_text(encoding='utf-8'))
        old = data.get('version')
        data['version'] = new_version
        CHROME_MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        log(f'Chrome manifest.json: {old} → {new_version}')

    if 'firefox' in targets and FIREFOX_MANIFEST.exists():
        data = json.loads(FIREFOX_MANIFEST.read_text(encoding='utf-8'))
        old = data.get('version')
        data['version'] = new_version
        FIREFOX_MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        log(f'Firefox manifest.json: {old} → {new_version}')

    if 'package' in targets and PACKAGE_JSON.exists():
        pkg = json.loads(PACKAGE_JSON.read_text(encoding='utf-8'))
        pkg_old = pkg.get('version')
        pkg['version'] = new_version
        PACKAGE_JSON.write_text(json.dumps(pkg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        log(f'package.json: {pkg_old} → {new_version}')


def npm_build(source_dir: Path) -> None:
    log(f'npm run build ({source_dir.relative_to(ROOT)}) ...')
    if not (source_dir / 'node_modules').exists():
        log('node_modules 不存在，先 npm install ...')
        run(['npm', 'install', '--registry', 'https://registry.npmmirror.com'], cwd=source_dir, timeout=300)
    run(['npm', 'run', 'build'], cwd=source_dir, timeout=300)


# ---------------------------------------------------------------------------
# Chrome 打包
# ---------------------------------------------------------------------------
def pack_chrome_crx(new_version: str) -> Path:
    """打包 Chrome crx3（纯 Python 实现，不依赖 Chrome 可执行文件）。

    crx3 格式：magic(4) + version(4) + header_len(4) + header_proto + zip
    header_proto 是 CrxFileHeader protobuf，含 AsymmetricKeyProof（SHA256 签名）。
    """
    if not PEM_FILE.exists():
        fail(f'未找到 Chrome 私钥: {PEM_FILE}')

    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    target = RELEASES_DIR / f'{EXT_NAME}-chrome-{new_version}.crx'

    log('Chrome: 打包中（纯 Python crx3，source.pem 保持扩展 ID）...')

    # 1. 把扩展目录打包成 zip（排除不需要的文件）
    import zipfile
    import tempfile

    zip_path = RELEASES_DIR / f'_tmp_{new_version}.zip'
    exclude_names = {'node_modules', '.git', 'src', 'package.json', 'package-lock.json',
                     'vue.config.js', 'babel.config.js', 'jsconfig.json', 'README-chrome.md'}
    exclude_exts = {'.md', '.pdf', '.xlsx'}

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(CHROME_SOURCE_DIR.rglob('*')):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(CHROME_SOURCE_DIR)
            # 跳过排除项
            if any(part in exclude_names for part in rel.parts):
                continue
            if rel.suffix in exclude_exts:
                continue
            zf.write(file_path, str(rel))

    zip_data = zip_path.read_bytes()
    zip_path.unlink()

    # 2. 用 RSA 私钥对 zip 的 SHA256 签名
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        log('cryptography 库未安装，正在自动安装...')
        run([sys.executable, '-m', 'pip', 'install', 'cryptography', '-i', 'https://mirrors.aliyun.com/pypi/simple/'], check=True)
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

    pem_data = PEM_FILE.read_bytes()
    private_key = serialization.load_pem_private_key(pem_data, password=None)
    public_key = private_key.public_key()

    # 导出公钥 DER（用于 protobuf header）
    pub_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # SHA256 签名
    signature = private_key.sign(zip_data, padding.PKCS1v15(), hashes.SHA256())

    # 3. 构造 CrxFileHeader protobuf（手工编码，无需 protobuf 库）
    # CrxFileHeader { repeated AsymmetricKeyProof signed_header_data = 10002; }
    # AsymmetricKeyProof { bytes public_key = 1; bytes signature = 2; }
    # AsymmetricKeyProof 是 message，需要 length-delimited 编码

    # 编码 AsymmetricKeyProof
    # field 1 (public_key): tag=0x0a (field1, wire type 2) + length + data
    akp_pubkey = b'\x0a' + _encode_varint(len(pub_der)) + pub_der
    # field 2 (signature): tag=0x12 (field2, wire type 2) + length + data
    akp_sig = b'\x12' + _encode_varint(len(signature)) + signature
    akp_data = akp_pubkey + akp_sig

    # 编码 CrxFileHeader.signed_header_data (field 10002)
    # field 10002, wire type 2 (length-delimited): tag = 10002 << 3 | 2 = 80018
    header_field_tag = _encode_varint((10002 << 3) | 2)
    header_field = header_field_tag + _encode_varint(len(akp_data)) + akp_data

    # 4. 组装 crx3 文件
    magic = b'Cr24'
    version = (3).to_bytes(4, 'little')
    header_len = len(header_field).to_bytes(4, 'little')

    with open(target, 'wb') as f:
        f.write(magic)
        f.write(version)
        f.write(header_len)
        f.write(header_field)
        f.write(zip_data)

    log(f'✅ Chrome crx: {target.name} ({target.stat().st_size // 1024}KB)')
    return target


def _encode_varint(value: int) -> bytes:
    """编码 protobuf varint。"""
    result = b''
    while value > 0x7f:
        result += bytes([(value & 0x7f) | 0x80])
        value >>= 7
    result += bytes([value])
    return result


def update_chrome_xml(new_version: str, crx_filename: str) -> None:
    codebase = f'{GITHUB_PAGES_BASE}/releases/{crx_filename}'
    content = f"""<?xml version='1.0' encoding='UTF-8'?>
<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>
  <app appid='{CHROME_EXT_ID}'>
    <updatecheck codebase='{codebase}' version='{new_version}' />
  </app>
</gupdate>
"""
    CHROME_UPDATE_XML.write_text(content, encoding='utf-8')
    log(f'✅ Chrome update.xml: v{new_version}')


# ---------------------------------------------------------------------------
# Firefox 打包
# ---------------------------------------------------------------------------
def find_web_ext() -> str:
    if shutil.which('web-ext'):
        return 'web-ext'
    local = ROOT / 'node_modules' / '.bin' / 'web-ext'
    if local.exists():
        return str(local)
    fail('未找到 web-ext。安装: npm install -g web-ext')


def _load_amo_keys_from_rc() -> tuple[str, str]:
    """从 ~/.zshrc 或 ~/.bashrc 读取 AMO 密钥（用户可能改了 rc 但当前 shell 没 source）。"""
    import re as _re
    home = Path.home()
    issuer = ''
    secret = ''
    for rc_name in ['.zshrc', '.bashrc', '.bash_profile', '.profile']:
        rc_path = home / rc_name
        if not rc_path.exists():
            continue
        try:
            content = rc_path.read_text(encoding='utf-8', errors='ignore')
            # 匹配 export AMO_JWT_ISSUER="..." 或 export AMO_JWT_ISSUER=...
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('#'):
                    continue
                m = _re.match(r'export\s+AMO_JWT_ISSUER\s*=\s*["\']?([^"\'\s]+)["\']?', line)
                if m and not issuer:
                    issuer = m.group(1)
                m = _re.match(r'export\s+AMO_JWT_SECRET\s*=\s*["\']?([^"\'\s]+)["\']?', line)
                if m and not secret:
                    secret = m.group(1)
            if issuer and secret:
                break
        except Exception:
            continue
    if issuer:
        log(f'从 rc 文件读到 AMO_JWT_ISSUER: {issuer[:10]}...')
    return issuer, secret


def pack_firefox_xpi(new_version: str, do_sign: bool = False) -> Path:
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    web_ext = find_web_ext()

    if do_sign:
        issuer = os.environ.get('AMO_JWT_ISSUER')
        secret = os.environ.get('AMO_JWT_SECRET')
        # 如果环境变量为空，尝试从 rc 文件加载（用户可能改了 rc 但没 source）
        if not issuer or not secret:
            issuer, secret = _load_amo_keys_from_rc()
        if not issuer or not secret:
            fail(
                'Firefox 签名需要 AMO 密钥，但未找到。请检查：\n'
                '  1. 确认 ~/.zshrc 或 ~/.bashrc 里有 export AMO_JWT_ISSUER=... 和 AMO_JWT_SECRET=...\n'
                '  2. 在当前终端执行: source ~/.zshrc（或重新打开终端）\n'
                '  3. 或直接在命令前加: AMO_JWT_ISSUER=xxx AMO_JWT_SECRET=xxx python3 scripts/release.py ...\n'
                '密钥获取: https://addons.mozilla.org/developers/addon/api/key/'
            )
        log('Firefox: web-ext sign（AMO 签名，unlisted 不公开上架）...')
        log('  ⏳ AMO 签名需要等待审核，可能数分钟到数小时，请耐心等待...')
        run([web_ext, 'sign', '--source-dir', str(FIREFOX_SOURCE_DIR),
             '--api-key', issuer, '--api-secret', secret,
             '--channel', 'unlisted',
             '--artifacts-dir', str(RELEASES_DIR)], cwd=FIREFOX_SOURCE_DIR, timeout=900)
    else:
        log('Firefox: web-ext build（不签名）...')
        run([web_ext, 'build', '--source-dir', str(FIREFOX_SOURCE_DIR),
             '--artifacts-dir', str(RELEASES_DIR),
             '--ignore-files', 'README-firefox.md', '*.md'], cwd=FIREFOX_SOURCE_DIR, timeout=60)

    # web-ext 默认输出 .zip（Firefox 的 xpi 本质就是 zip），找最新的 zip/xpi
    xpi_files = sorted(
        list(RELEASES_DIR.glob('*.xpi')) + list(RELEASES_DIR.glob('*.zip')),
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    # 排除我们自己的 crx 临时文件
    xpi_files = [f for f in xpi_files if not f.name.startswith('_tmp_')]
    if not xpi_files:
        fail('web-ext 未生成 xpi/zip。')

    target = RELEASES_DIR / f'{EXT_NAME}-firefox-{new_version}.xpi'
    if xpi_files[0] != target:
        shutil.copy2(xpi_files[0], target)
    log(f'✅ Firefox xpi: {target.name} ({target.stat().st_size // 1024}KB)')
    if not do_sign:
        log('⚠️  未签名 xpi 无法被 Firefox 永久安装/自动更新！用 --sign 签名。')
    return target


def update_firefox_json(new_version: str, xpi_filename: str, xpi_path: Path) -> None:
    update_link = f'{GITHUB_PAGES_BASE}/releases/{xpi_filename}'
    update_hash = sha256_file(xpi_path)

    # 合并历史版本
    # 先从 release-main 分支读取现有 updates.json
    existing: dict = {}
    try:
        result = subprocess.run(['git', 'show', f'{RELEASE_BRANCH}:updates.json'], cwd=str(ROOT), capture_output=True, text=True)
        if result.returncode == 0:
            existing = json.loads(result.stdout)
    except Exception:
        pass

    updates_list = existing.get('addons', {}).get(FIREFOX_EXT_ID, {}).get('updates', [])
    updates_list = [u for u in updates_list if u.get('version') != new_version]
    updates_list.insert(0, {
        'version': new_version,
        'update_link': update_link,
        'update_hash': update_hash,
        'applications': {'gecko': {'strict_min_version': FIREFOX_MIN_VERSION}},
    })
    data = {'addons': {FIREFOX_EXT_ID: {'updates': updates_list}}}
    FIREFOX_UPDATES_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    log(f'✅ Firefox updates.json: v{new_version}')


# ---------------------------------------------------------------------------
# 同步到 release-main 分支并推送
# ---------------------------------------------------------------------------
def sync_to_release_branch(new_version: str) -> None:
    """把 _dist_release/ 产物同步到 release-main 分支，提交并推送。"""
    log(f'同步产物到 {RELEASE_BRANCH} 分支...')

    # 确保在 master 分支（避免误操作）
    current = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    if current == RELEASE_BRANCH:
        fail(f'当前已在 {RELEASE_BRANCH} 分支，发版脚本应在 master 分支执行。')

    # 检查工作区是否干净（release-main 操作需要切换分支）
    status = subprocess.run(['git', 'status', '--porcelain'], cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    # 只忽略 _dist_release 相关的变更
    dirty = [l for l in status.split('\n') if l and '_dist_release' not in l and 'scripts/' not in l]
    if dirty:
        log('⚠️ 工作区有未提交的变更（非 _dist_release/scripts），建议先提交：')
        for l in dirty[:5]:
            print(f'    {l}')
        resp = input('继续可能丢失这些变更，确认继续？(y/N) ')
        if resp.lower() != 'y':
            fail('用户取消。请先提交或 stash 工作区变更。')

    # 用 git stash 临时保存工作区（含 _dist_release，因为它是 untracked）
    log('临时保存工作区...')
    subprocess.run(['git', 'stash', 'push', '-u', '-m', 'release-temp'], cwd=str(ROOT), capture_output=True)

    try:
        # 切到 release-main
        subprocess.run(['git', 'checkout', RELEASE_BRANCH], cwd=str(ROOT), check=True, capture_output=True)

        # 把产物从 _dist_release 复制到 release-main 根目录
        for item in DIST_DIR.iterdir():
            dest = ROOT / item.name
            if dest.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # 提交
        # 更新 HTML 中的版本号显示（install.html / install-firefox.html / index.html）
        import glob as _glob
        for _html_file in ['index.html', 'install.html', 'install-firefox.html']:
            _hp = ROOT / _html_file
            if _hp.exists():
                _content = _hp.read_text(encoding='utf-8')
                # 替换所有旧版本号引用（如 3.3.0 → 3.5.0）
                import re as _re2
                _content = _re2.sub(r'\d+\.\d+\.\d+', new_version, _content)
                _content = _content.replace('vX.Y.Z', f'v{new_version}')
                _hp.write_text(_content, encoding='utf-8')
                log(f'✅ 更新版本号: {_html_file} → v{new_version}')
        subprocess.run(['git', 'add', '-A'], cwd=str(ROOT), check=True, capture_output=True)
        commit_result = subprocess.run(
            ['git', 'commit', '-m', f'release: v{new_version}'],
            cwd=str(ROOT), capture_output=True, text=True
        )
        if commit_result.returncode == 0:
            log(f'✅ 已提交到 {RELEASE_BRANCH}')
        else:
            log(f'提交无变更（可能版本相同）: {commit_result.stdout.strip()[:100]}')

        # 推送
        log(f'推送到 {RELEASE_REMOTE}...')
        push_result = subprocess.run(
            ['git', 'push', RELEASE_REMOTE, f'{RELEASE_BRANCH}:main'],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120
        )
        if push_result.returncode == 0:
            log('✅ 推送成功！GitHub Pages 将在 1-2 分钟后生效。')
        else:
            log(f'⚠️ 推送失败: {push_result.stderr[:200]}')
            log(f'   可手动推送: git push {RELEASE_REMOTE} {RELEASE_BRANCH}:main')

    finally:
        # 切回 master 并恢复工作区
        subprocess.run(['git', 'checkout', '-f', current], cwd=str(ROOT), capture_output=True)
        subprocess.run(['git', 'stash', 'pop'], cwd=str(ROOT), capture_output=True)
        log(f'已切回 {current} 分支并恢复工作区。')


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description='JIRA 效率助手打包发版脚本')
    parser.add_argument('version', help='新版本号 X.Y.Z，例: 3.4.0')
    parser.add_argument('--chrome', action='store_true', help='只打包 Chrome')
    parser.add_argument('--firefox', action='store_true', help='只打包 Firefox')
    parser.add_argument('--sign', action='store_true', help='Firefox 签名（需 AMO 密钥）')
    parser.add_argument('--no-build', action='store_true', help='跳过 npm run build')
    parser.add_argument('--no-pack', action='store_true', help='跳过打包（使用已有 crx/xpi）')
    parser.add_argument('--no-push', action='store_true', help='只打包不推送到 GitHub')
    parser.add_argument('--build-only', action='store_true', help='只更新版本号 + npm build（不打包不推送）')
    parser.add_argument('--release-only', action='store_true', help='只更新版本号+生成清单+推送（跳过编译和打包，手动签名后用）')
    args = parser.parse_args()

    # --build-only 等于 --no-pack --no-push
    if args.build_only:
        args.no_pack = True
        args.no_push = True
    # --release-only 等于 --no-build --no-pack（用已有 crx/xpi，跳过编译和打包，但仍然推送）
    if args.release_only:
        args.no_build = True
        args.no_pack = True

    do_chrome = args.chrome or not args.firefox
    do_firefox = args.firefox or not args.chrome
    new_version = args.version

    log(f'═══ 发版 v{new_version} (Chrome={do_chrome}, Firefox={do_firefox}, sign={args.sign}) ═══')

    # 准备输出目录
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 改版本号
    targets = ['package']
    if do_chrome:
        targets.append('chrome')
    if do_firefox:
        targets.append('firefox')
    bump_version(new_version, targets)

    # 2. npm build
    if not args.no_build:
        if do_chrome:
            npm_build(CHROME_SOURCE_DIR)
        if do_firefox:
            npm_build(FIREFOX_SOURCE_DIR)

    # --build-only: 只更新版本号 + 编译，到此结束，不打包不推送
    if args.build_only:
        log('✅ --build-only 完成：版本号已更新，npm build 已完成。')
        return

    # 3+4. 打包 + 生成清单（Chrome 和 Firefox 独立，一方失败不阻塞另一方）
    chrome_ok = False
    firefox_ok = False

    if do_chrome:
        try:
            if not args.no_pack:
                crx_path = pack_chrome_crx(new_version)
            else:
                crx_path = RELEASES_DIR / f'{EXT_NAME}-chrome-{new_version}.crx'
                if not crx_path.exists():
                    log(f'⚠️ 未找到 Chrome crx: {crx_path}')
                    log(f'   请手动打包后放到: _dist_release/releases/jira-helper-chrome-{new_version}.crx')
                    log(f'   打包方式: chrome://extensions → 打包扩展程序 → 选 input/source + input/source.pem')
                    raise FileNotFoundError(f'未找到 crx: {crx_path}')
            update_chrome_xml(new_version, crx_path.name)
            chrome_ok = True
        except Exception as e:
            log(f'⚠️ Chrome 打包失败（跳过）: {e}')

    if do_firefox:
        try:
            if not args.no_pack:
                xpi_path = pack_firefox_xpi(new_version, do_sign=args.sign)
            else:
                xpi_path = RELEASES_DIR / f'{EXT_NAME}-firefox-{new_version}.xpi'
                if not xpi_path.exists():
                    log(f'⚠️ 未找到 Firefox xpi: {xpi_path}')
                    log(f'   请手动签名后放到: _dist_release/releases/jira-helper-firefox-{new_version}.xpi')
                    log(f'   签名方式: AMO 后台上传 → 审核通过后下载签名 xpi')
                    raise FileNotFoundError(f'未找到 xpi: {xpi_path}')
            update_firefox_json(new_version, xpi_path.name, xpi_path)
            firefox_ok = True
        except (Exception, SystemExit) as e:
            msg = str(e) if not isinstance(e, SystemExit) else 'Firefox 签名/打包失败'
            log(f'⚠️ Firefox 打包失败（跳过）: {msg}')
            if args.sign:
                log('  提示: --sign 需要 AMO 密钥，未配置则 Firefox 签名会失败。')
                log('  可用 --chrome 只发 Chrome，或配置 AMO 密钥后再发 Firefox。')

    if not chrome_ok and not firefox_ok:
        fail('Chrome 和 Firefox 均打包失败，请检查错误信息。')

    log('═══ 打包完成 ═══')
    log(f'产物目录: {DIST_DIR}')
    for item in sorted(DIST_DIR.rglob('*')):
        if item.is_file():
            log(f'  {item.relative_to(DIST_DIR)} ({item.stat().st_size // 1024}KB)')

    # 5. 同步到 release-main 并推送
    if not args.no_push:
        print()
        sync_to_release_branch(new_version)
    else:
        log('--no-push: 跳过推送。产物在 _dist_release/ 可检查。')


if __name__ == '__main__':
    main()
