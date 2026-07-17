# JIRA 效率助手 — GitHub Pages 自动更新部署指南（Chrome + Firefox）

本指南面向插件开发者/维护者，说明如何用 GitHub Pages 托管 `.crx`/`.xpi` 实现双浏览器自动更新分发。

---

## ⚡ 快速发版（TL;DR）

```bash
cd /home/ts/Cursor/0214test
source .venv/bin/activate          # 激活虚拟环境（必须！）
git checkout master                 # 确保在 master 分支
python3 scripts/release.py 3.4.0 --chrome   # 发版（Chrome）
```

脚本自动完成：打包 → 推送到 release-main → 切回 master。推送后 1-2 分钟 GitHub Pages 生效。

---

## 一、整体架构

```
GitHub 仓库 (shug666/JIRA_Efficiency_Assistant) ← 公开分发仓库
│
├── index.html               ← 门户首页（Chrome/Firefox 双入口）
├── install.html             ← Chrome 安装指南
├── install-firefox.html     ← Firefox 安装指南
├── update.xml               ← Chrome 自动更新清单（每 5h 拉取）
├── updates.json             ← Firefox 自动更新清单
├── .nojekyll                ← 禁用 Jekyll
├── releases/
│   ├── jira-helper-chrome-X.Y.Z.crx
│   └── jira-helper-firefox-X.Y.Z.xpi
└── scripts/release.py       ← 发版脚本（在 master 分支执行）
```

### 关键参数

| 参数 | Chrome | Firefox |
|------|--------|---------|
| 扩展 ID | `inmachhhbcehlpklfjgenplmgffbiiaf` | `jira-template-manager@shugan` |
| 更新清单 | `update.xml` (XML) | `updates.json` (JSON) |
| 检查频率 | 每 5 小时 | 约每天 1 次 |
| 签名要求 | source.pem 自签（Python crx3） | **必须 AMO 签名** |
| 安装包格式 | `.crx` | `.xpi` |

### Git 分支模型

```
master        ← 开发分支（有源码 input/source、output/firefox、source.pem）
                 在此分支执行 scripts/release.py
release-main  ← 分发分支（只有产物：crx/xpi/update.xml 等）
                 脚本自动切到此处提交产物，推送到 GitHub
```

---

## 二、发版前置条件（一次性配置）

### 2.1 激活虚拟环境

**每次发版前必须先激活虚拟环境**，否则 `cryptography` 库会找不到。

```bash
cd /home/ts/Cursor/0214test
source .venv/bin/activate

# 确认已激活（提示符显示 (.venv)，且 which python3 指向 .venv）
which python3
# → /home/ts/Cursor/0214test/.venv/bin/python3

# 首次需安装 cryptography（仅一次）
pip install cryptography -i https://mirrors.aliyun.com/pypi/simple/
```

发版完成后退出虚拟环境：
```bash
deactivate
```

### 2.2 确认在 master 分支

```bash
git checkout master
# 发版脚本会在 master 打包，自动切到 release-main 推送，再切回 master
```

### 2.3（Firefox 签名才需要）配置 AMO 密钥

Firefox 扩展必须签名才能永久安装和自动更新。如需发 Firefox 签名版：

1. 注册 https://addons.mozilla.org/developers/
2. 获取 API 密钥：https://addons.mozilla.org/developers/addon/api/key/
3. 配置环境变量（写入 `~/.bashrc` 或 `~/.zshrc`）：
   ```bash
   export AMO_JWT_ISSUER=user:12345678:123
   export AMO_JWT_SECRET=你的secret
   ```

---

## 三、日常发版流程

### 3.1 激活环境 + 发版

```bash
# 1. 激活虚拟环境
cd /home/ts/Cursor/0214test
source .venv/bin/activate

# 2. 确保在 master 分支
git checkout master

# 3. 执行发版（按需选一种）

# 只发 Chrome（推荐，无需任何密钥）
python3 scripts/release.py 3.4.0 --chrome

# 发 Chrome + Firefox（Firefox 不签名，仅供临时调试）
python3 scripts/release.py 3.4.0

# 发 Chrome + Firefox 签名版（需先配 AMO 密钥）
python3 scripts/release.py 3.4.0 --sign
```

### 3.2 脚本自动完成的工作

```
1. 改版本号（Chrome manifest + Firefox manifest + package.json）
2. npm run build（Vue SPA，两端各自构建）
3a. Chrome: 纯 Python crx3 打包（cryptography 库签名，不依赖 Chrome 可执行文件）
3b. Firefox: web-ext 打包/签名 xpi
4. 生成 update.xml / updates.json
5. git stash → 切到 release-main → 复制产物 → 提交 → 推送 → 切回 master → git stash pop
```

推送后 1-2 分钟，GitHub Pages 生效，用户端浏览器自动更新。

### 3.3 命令参数说明

| 命令 | Chrome | Firefox | 需要密钥 |
|------|--------|---------|---------|
| `release.py 3.4.0` | ✅ 打包推送 | ✅ 打包（不签名） | ❌ |
| `release.py 3.4.0 --chrome` | ✅ 打包推送 | ❌ 跳过 | ❌ |
| `release.py 3.4.0 --firefox` | ❌ 跳过 | ✅ 打包（不签名） | ❌ |
| `release.py 3.4.0 --firefox --sign` | ❌ 跳过 | ✅ 签名打包 | ✅ 需 AMO |
| `release.py 3.4.0 --sign` | ✅ 打包推送 | ✅ 签名打包 | ✅ 需 AMO |
| `release.py 3.4.0 --no-build` | 跳过构建 | 跳过构建 | — |
| `release.py 3.4.0 --no-push` | 只打包不推送 | 只打包不推送 | — |

---

## 四、验证自动更新

### Chrome

1. 从 https://shug666.github.io/JIRA_Efficiency_Assistant/ 下载安装 crx
2. 发新版
3. `chrome://extensions/` → 点「更新」
4. 观察版本号变化

### Firefox

1. 安装签名过的 xpi
2. 发新版
3. `about:addons` → 齿轮 → 「检查更新」
4. 观察版本号变化

---

## 五、常见问题

### `ModuleNotFoundError: No module named 'cryptography'`

**原因**：没有激活虚拟环境，或虚拟环境里没装 cryptography。

**解决**：
```bash
source .venv/bin/activate
pip install cryptography -i https://mirrors.aliyun.com/pypi/simple/
```

### `Firefox 签名需要环境变量 AMO_JWT_ISSUER 和 AMO_JWT_SECRET`

**原因**：`--sign` 需要 AMO 密钥但未配置。

**解决**：要么用 `--chrome` 只发 Chrome（不需要密钥），要么按 2.3 节配置 AMO 密钥。

### Chrome crx 打包失败

**原因**：新版 Chrome headless 模式不再支持 `--pack-extension`。

**现状**：脚本已改用纯 Python crx3 打包（cryptography 库），不依赖 Chrome 可执行文件。确保虚拟环境有 cryptography 即可。

### 推送失败 / 超时

crx 文件较大（3-4MB），推送可能需要 30 秒以上。脚本设置了 120 秒超时。如仍失败：
```bash
git checkout release-main
git push release release-main:main
git checkout master
```

---

## 六、安全注意事项

### source.pem（Chrome 私钥）

- **绝对不入 git**（已加入 .gitignore）
- **绝不丢失**（丢失 = 失去 Chrome 扩展 ID = 所有用户无法更新）
- 备份到密码管理器 / 加密 U 盘

### AMO API 密钥（Firefox 签名）

- 不要硬编码到脚本，用环境变量
- 可在 AMO 后台随时重新生成

---

## 七、Chrome vs Firefox 更新机制对比

```
                Chrome                      Firefox
              ─────────                  ──────────
清单格式      XML (update.xml)           JSON (updates.json)
签名要求      无（pem 自签）             必须 AMO 签名
检查频率      每 5 小时                  约每天 1 次
首次安装      拖拽 crx（开发者模式）     双击签名 xpi / about:debugging
自动更新      ✅ 原生支持                ✅ 需签名 xpi
未签名后果    不适用（Chrome 不签名）    只能临时加载，无自动更新
扩展 ID       pem 指纹（32位）           gecko.id（自定义字符串）
打包方式      Python crx3（cryptography） web-ext（npm 工具）
```

---

*本指南由 scripts/release.py 维护。*
