#!/usr/bin/env python3
"""JIRA 效率助手 — 一键打包发版脚本（Chrome + Firefox 双版本）
============================================================

完成以下工作：
  1. 同步修改 Chrome/Firefox manifest.json + package.json 的版本号
  2. npm run build（Vue SPA，两端共用）
  3a. Chrome: 用 source.pem 打包 crx（保持扩展 ID 不变）
  3b. Firefox: 用 web-ext 打包 xpi（需 AMO 签名才能自动更新）
  4a. 更新 docs/update.xml (Chrome 自动更新清单)
  4b. 更新 docs/updates.json (Firefox 自动更新清单)
  5. 输出 git 提交提示

用法
----
  python3 scripts/release.py <版本号>                      # 打包两端
  python3 scripts/release.py <版本号> --chrome             # 只打包 Chrome
  python3 scripts/release.py <版本号> --firefox            # 只打包 Firefox
  python3 scripts/release.py <版本号> --no-build           # 跳过 npm run build
  python3 scripts/release.py <版本号> --firefox --sign     # Firefox 签名（需 AMO 密钥）
  python3 scripts/release.py <版本号> --no-pack            # 跳过打包（使用已有产物）

前置条件
--------
  Chrome:
    - input/source.pem 私钥
    - Google Chrome / Chromium
    - 已 cd input/source && npm install

  Firefox:
    - output/firefox/ 目录已组装好
    - 已 cd output/firefox && npm install
    - web-ext 工具（npm install -g web-ext）
    - AMO 签名（可选，见 --sign）：https://addons.mozilla.org/developers/addon/api/key/

之后把生成的 crx/xpi 和 update 清单 commit + push 即可。
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

# Chrome
CHROME_SOURCE_DIR = ROOT / 'input' / 'source'
CHROME_MANIFEST = CHROME_SOURCE_DIR / 'manifest.json'
PEM_FILE = ROOT / 'input' / 'source.pem'

# Firefox
FIREFOX_SOURCE_DIR = ROOT / 'output' / 'firefox'
FIREFOX_MANIFEST = FIREFOX_SOURCE_DIR / 'manifest.json'

# 共用
PACKAGE_JSON = CHROME_SOURCE_DIR / 'package.json'

# 输出（根目录模式，适配 GitHub Pages / (root) 配置）
DOCS_DIR = ROOT  # 直接用根目录
RELEASES_DIR = ROOT / 'releases'
CHROME_UPDATE_XML = ROOT / 'update.xml'
FIREFOX_UPDATES_JSON = ROOT / 'updates.json'

# 常量
GITHUB_PAGES_BASE = 'https://shug666.github.io/JIRA_Efficiency_Assistant'
CHROME_EXT_ID = 'inmachhhbcehlpklfjgenplmgffbiiaf'
FIREFOX_EXT_ID = 'jira-template-manager@shugan'
FIREFOX_MIN_VERSION = '128.0'
EXT_NAME = 'jira-helper'  # 文件名前缀（英文，确保下载链接稳定）


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def log(msg: str) -> None:
    print(f'[release] {msg}')


def fail(msg: str, code: int = 1) -> None:
    print(f'[release][错误] {msg}', file=sys.stderr)
    sys.exit(code)


def run(cmd: list[str] | str, cwd: Path | None = None, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    log(f'$ {cmd if isinstance(cmd, str) else " ".join(cmd)}')
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=check, env=env, text=True, capture_output=True)
    if result.stdout and result.stdout.strip():
        print(result.stdout.rstrip()[:500])  # 截断过长输出
    return result


def find_chrome() -> str:
    candidates = [
        'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser',
        '/opt/google/chrome/chrome', '/usr/bin/google-chrome',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    ]
    for c in candidates:
        if shutil.which(c) or os.path.exists(c):
            return c
    fail('未找到 Chrome / Chromium 可执行文件，请安装或手动指定。')


def sha256_file(path: Path) -> str:
    """计算文件 SHA256，返回 base64 格式（Firefox update_hash 用）。"""
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
    """修改指定 manifest 的版本号。targets 含 'chrome'/'firefox'/'package'。"""
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
    log(f'在 {source_dir.relative_to(ROOT)} 执行 npm run build ...')
    if not (source_dir / 'node_modules').exists():
        log('node_modules 不存在，先 npm install ...')
        run(['npm', 'install', '--registry', 'https://registry.npmmirror.com'], cwd=source_dir)
    run(['npm', 'run', 'build'], cwd=source_dir)


# ---------------------------------------------------------------------------
# Chrome 打包
# ---------------------------------------------------------------------------
def pack_chrome_crx(new_version: str) -> Path:
    if not PEM_FILE.exists():
        fail(f'未找到 Chrome 私钥: {PEM_FILE}')

    chrome = find_chrome()
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)

    crx_out = CHROME_SOURCE_DIR / 'source.crx'
    if crx_out.exists():
        crx_out.unlink()

    log('Chrome: 调用 Chrome 打包（source.pem 保持扩展 ID 不变）...')
    cmd = [
        chrome,
        f'--pack-extension={CHROME_SOURCE_DIR}',
        f'--pack-extension-key={PEM_FILE}',
        '--no-message-box', '--headless=new', '--disable-gpu', '--no-sandbox',
    ]
    proc = run(cmd, check=False)
    if not crx_out.exists():
        fail(
            'Chrome 打包未生成 crx。\n'
            f'  stdout: {proc.stdout}\n  stderr: {proc.stderr}\n'
            '可改用 chrome://extensions → 打包扩展程序 手动打包。'
        )

    target = RELEASES_DIR / f'{EXT_NAME}-chrome-{new_version}.crx'
    shutil.copy2(crx_out, target)
    log(f'Chrome crx 已生成: {target.relative_to(ROOT)}')
    return target


def update_chrome_xml(new_version: str, crx_filename: str) -> None:
    codebase = f'{GITHUB_PAGES_BASE}/releases/{crx_filename}'
    content = f"""<?xml version='1.0' encoding='UTF-8'?>
<!--
  Chrome 扩展自动更新清单（由 scripts/release.py 自动生成，请勿手动修改）
  Chrome 每 5 小时拉取本文件，对比 version 决定是否下载 codebase 指向的 crx。
-->
<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>
  <app appid='{CHROME_EXT_ID}'>
    <updatecheck codebase='{codebase}' version='{new_version}' />
  </app>
</gupdate>
"""
    CHROME_UPDATE_XML.write_text(content, encoding='utf-8')
    log(f'Chrome update.xml 已更新: version={new_version}')


# ---------------------------------------------------------------------------
# Firefox 打包
# ---------------------------------------------------------------------------
def find_web_ext() -> str:
    """寻找 web-ext 可执行文件。"""
    # 1. 全局安装
    if shutil.which('web-ext'):
        return 'web-ext'
    # 2. 本地 node_modules
    local = ROOT / 'node_modules' / '.bin' / 'web-ext'
    if local.exists():
        return str(local)
    fail('未找到 web-ext。请安装: npm install -g web-ext')


def pack_firefox_xpi(new_version: str, do_sign: bool = False) -> Path:
    """用 web-ext 打包（可选签名）Firefox xpi。"""
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    web_ext = find_web_ext()

    if do_sign:
        # 签名模式（需要 AMO API 密钥）
        issuer = os.environ.get('AMO_JWT_ISSUER')
        secret = os.environ.get('AMO_JWT_SECRET')
        if not issuer or not secret:
            fail(
                'Firefox 签名需要 AMO 密钥。请设置环境变量:\n'
                '  export AMO_JWT_ISSUER=your_issuer\n'
                '  export AMO_JWT_SECRET=your_secret\n'
                '密钥获取: https://addons.mozilla.org/developers/addon/api/key/'
            )
        log('Firefox: web-ext sign（AMO 签名）...')
        env = {**os.environ}
        cmd = [
            web_ext, 'sign',
            '--source-dir', str(FIREFOX_SOURCE_DIR),
            '--api-key', issuer,
            '--api-secret', secret,
            '--artifacts-dir', str(RELEASES_DIR),
        ]
        run(cmd, cwd=FIREFOX_SOURCE_DIR, env=env)
    else:
        # 仅打包（不签名，仅供临时调试或预览）
        log('Firefox: web-ext build（不签名，仅供临时安装）...')
        cmd = [
            web_ext, 'build',
            '--source-dir', str(FIREFOX_SOURCE_DIR),
            '--artifacts-dir', str(RELEASES_DIR),
            '--ignore-files', 'README-firefox.md', '*.md',
        ]
        run(cmd, cwd=FIREFOX_SOURCE_DIR)

    # web-ext 默认输出文件名: jira_template_manager-3.4.0.xpi（基于 gecko.id 或 package name）
    # 找到刚生成的 xpi 并改名
    xpi_files = sorted(RELEASES_DIR.glob('*.xpi'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not xpi_files:
        fail('web-ext 未生成 xpi 文件。检查 web-ext 输出日志。')

    target = RELEASES_DIR / f'{EXT_NAME}-firefox-{new_version}.xpi'
    if xpi_files[0] != target:
        shutil.copy2(xpi_files[0], target)
    log(f'Firefox xpi 已生成: {target.relative_to(ROOT)}')

    if not do_sign:
        log('⚠️  未签名的 xpi 无法被 Firefox 永久安装/自动更新！')
        log('    如需自动更新，请用 --sign 参数并配置 AMO 密钥。')

    return target


def update_firefox_json(new_version: str, xpi_filename: str, xpi_path: Path) -> None:
    """更新 docs/updates.json。"""
    update_link = f'{GITHUB_PAGES_BASE}/releases/{xpi_filename}'
    update_hash = sha256_file(xpi_path)

    # 读取现有 updates.json，追加新版本（保留历史版本记录）
    existing: dict = {}
    if FIREFOX_UPDATES_JSON.exists():
        try:
            existing = json.loads(FIREFOX_UPDATES_JSON.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            log('⚠️ 现有 updates.json 解析失败，将覆盖重建。')

    updates_list = existing.get('addons', {}).get(FIREFOX_EXT_ID, {}).get('updates', [])
    # 去重：移除同版本旧记录
    updates_list = [u for u in updates_list if u.get('version') != new_version]
    # 新版本插到最前
    updates_list.insert(0, {
        'version': new_version,
        'update_link': update_link,
        'update_hash': update_hash,
        'applications': {'gecko': {'strict_min_version': FIREFOX_MIN_VERSION}},
    })

    data = {
        'addons': {
            FIREFOX_EXT_ID: {'updates': updates_list}
        }
    }
    FIREFOX_UPDATES_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    log(f'Firefox updates.json 已更新: version={new_version}')


# ---------------------------------------------------------------------------
# 收尾
# ---------------------------------------------------------------------------
def print_git_hint(new_version: str, did_chrome: bool, did_firefox: bool) -> None:
    log('全部完成！执行以下命令发布：')
    print()
    print('  git add docs/ \\')
    if did_chrome:
        print('    input/source/manifest.json input/source/package.json \\')
    if did_firefox:
        print('    output/firefox/manifest.json \\')
    print(f'    scripts/release.py')
    print(f'  git commit -m "release: v{new_version}"')
    print('  git push origin main')
    print()
    print('推送后 1-2 分钟 GitHub Pages 生效：')
    if did_chrome:
        print('  Chrome: 已装扩展每 5h 自动更新')
    if did_firefox:
        print('  Firefox: 已装（且已签名）扩展会自动检查 updates.json')


def main() -> None:
    parser = argparse.ArgumentParser(description='JIRA 效率助手打包发版脚本（Chrome + Firefox）')
    parser.add_argument('version', help='新版本号 X.Y.Z，例: 3.4.0')
    parser.add_argument('--chrome', action='store_true', help='只打包 Chrome')
    parser.add_argument('--firefox', action='store_true', help='只打包 Firefox')
    parser.add_argument('--sign', action='store_true', help='Firefox 签名（需 AMO_JWT_ISSUER/AMO_JWT_SECRET）')
    parser.add_argument('--no-build', action='store_true', help='跳过 npm run build')
    parser.add_argument('--no-pack', action='store_true', help='跳过打包（使用已有 crx/xpi）')
    args = parser.parse_args()

    # 决定打包哪些端（默认两端都打）
    do_chrome = args.chrome or not args.firefox
    do_firefox = args.firefox or not args.chrome

    new_version = args.version
    log(f'开始发版 v{new_version} (Chrome={do_chrome}, Firefox={do_firefox}, sign={args.sign})')
    log(f'仓库根目录: {ROOT}')

    targets = ['package']
    if do_chrome:
        targets.append('chrome')
    if do_firefox:
        targets.append('firefox')

    # 1. 改版本号
    bump_version(new_version, targets)

    # 2. npm build
    if not args.no_build:
        if do_chrome:
            npm_build(CHROME_SOURCE_DIR)
        if do_firefox:
            npm_build(FIREFOX_SOURCE_DIR)

    # 3+4. 打包 + 更新清单
    if do_chrome:
        if not args.no_pack:
            crx_path = pack_chrome_crx(new_version)
        else:
            crx_path = RELEASES_DIR / f'{EXT_NAME}-chrome-{new_version}.crx'
            if not crx_path.exists():
                fail(f'--no-pack 模式下未找到 crx: {crx_path}')
        update_chrome_xml(new_version, crx_path.name)

    if do_firefox:
        if not args.no_pack:
            xpi_path = pack_firefox_xpi(new_version, do_sign=args.sign)
        else:
            xpi_path = RELEASES_DIR / f'{EXT_NAME}-firefox-{new_version}.xpi'
            if not xpi_path.exists():
                fail(f'--no-pack 模式下未找到 xpi: {xpi_path}')
        update_firefox_json(new_version, xpi_path.name, xpi_path)

    # 5. 提示
    print_git_hint(new_version, do_chrome, do_firefox)


if __name__ == '__main__':
    main()
