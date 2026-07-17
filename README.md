# JIRA 效率助手 — 浏览器扩展分发仓库

本仓库用于 **Chrome / Firefox 扩展的打包分发与自动更新**，通过 GitHub Pages 托管。

> 源码开发仓库：[JIRA-](https://github.com/shug666/JIRA-)（私有）
> 本仓库（JIRA_Efficiency_Assistant）：**公开分发 + 自动更新**

---

## 用户安装

访问 👉 **[安装指南](https://shug666.github.io/JIRA_Efficiency_Assistant/)**

- **Chrome / Edge**：下载 `.crx`，开发者模式拖拽安装，之后每 5 小时自动更新
- **Firefox**：下载 `.xpi`（需签名版），自动更新

---

## 仓库结构（根目录模式，GitHub Pages = /(root)）

```
index.html               ← 门户首页（Chrome/Firefox 双入口）
install.html             ← Chrome 安装指南
install-firefox.html     ← Firefox 安装指南
update.xml               ← Chrome 自动更新清单（每 5h 拉取）
updates.json             ← Firefox 自动更新清单
.nojekyll                ← 禁用 Jekyll
releases/
├── jira-helper-chrome-X.Y.Z.crx
└── jira-helper-firefox-X.Y.Z.xpi
```

## 自动更新原理

| | Chrome | Firefox |
|---|--------|---------|
| 扩展 ID | `inmachhhbcehlpklfjgenplmgffbiiaf` | `jira-template-manager@shugan` |
| 清单 | `update.xml` (XML) | `updates.json` (JSON) |
| 检查频率 | 每 5 小时 | 约每天 1 次 |
| 签名 | source.pem 自签 | 必须 AMO 签名 |

---

## 维护者发版

详细说明见 **[RELEASE-GUIDE.md](https://shug666.github.io/JIRA_Efficiency_Assistant/RELEASE-GUIDE.md)**

### 前置：切换到虚拟环境（每次发版前必须执行）

```bash
# 进入项目根目录
cd /home/ts/Cursor/0214test

# 激活虚拟环境（必须！否则 cryptography 库找不到）
source .venv/bin/activate

# 确认虚拟环境已激活（提示符应显示 (.venv)）
which python3
# 应输出: /home/ts/Cursor/0214test/.venv/bin/python3

# 如果 cryptography 未安装（首次发版需执行一次）
pip install cryptography -i https://mirrors.aliyun.com/pypi/simple/
```

### 发版命令

```bash
# ⚠️ 必须在 master 分支执行（不是 release-main）
git checkout master

# 只发 Chrome（推荐先跑通这个，无需任何密钥）
python3 scripts/release.py 3.4.0 --chrome

# 发 Chrome + Firefox（Firefox 不签名，仅供临时调试）
python3 scripts/release.py 3.4.0

# 发 Chrome + Firefox 签名版（需 AMO 密钥，见 RELEASE-GUIDE.md）
python3 scripts/release.py 3.4.0 --sign
```

脚本会自动完成：打包 → 切到 release-main → 提交 → 推送 → 切回 master。
推送后 GitHub Pages 1-2 分钟生效，用户端浏览器自动更新。

### 退出虚拟环境

```bash
deactivate
