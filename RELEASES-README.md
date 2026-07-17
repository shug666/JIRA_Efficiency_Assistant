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

## 仓库结构

```
docs/                        ← GitHub Pages 源（Settings → Pages → main/docs）
├── index.html               ← 门户首页（Chrome/Firefox 双入口）
├── install.html             ← Chrome 安装指南
├── install-firefox.html     ← Firefox 安装指南
├── update.xml               ← Chrome 自动更新清单
├── updates.json             ← Firefox 自动更新清单
├── .nojekyll                ← 禁用 Jekyll
└── releases/
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

见 [RELEASE-GUIDE.md](https://shug666.github.io/JIRA_Efficiency_Assistant/RELEASE-GUIDE.md)

```bash
# 一键发版（双端）
python3 scripts/release.py 3.4.0 --sign

# 提交推送
git add docs/ && git commit -m "release: v3.4.0" && git push
