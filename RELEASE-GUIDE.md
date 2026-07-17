# JIRA 效率助手 — GitHub Pages 自动更新部署指南（Chrome + Firefox）

本指南面向插件开发者/维护者，说明如何用 GitHub Pages 托管 `.crx`/`.xpi` 实现双浏览器自动更新分发。

---

## 一、整体架构

```
GitHub 仓库 (shug666/JIRA_Efficiency_Assistant)
│
├─ docs/                              ← GitHub Pages 源
│  ├─ index.html                      ← 门户首页（Chrome/Firefox 双入口）
│  ├─ install.html                    ← Chrome 图文安装指南
│  ├─ install-firefox.html            ← Firefox 图文安装指南
│  ├─ update.xml                      ← ⭐ Chrome 自动更新清单（每 5h 拉取）
│  ├─ updates.json                    ← ⭐ Firefox 自动更新清单
│  ├─ .nojekyll                       ← 禁用 Jekyll
│  └─ releases/
│     ├─ jira-helper-chrome-3.3.0.crx
│     └─ jira-helper-firefox-3.3.0.xpi
│
├─ input/source/                      ← Chrome 源码
│  ├─ manifest.json                   ← update_url 指向 GitHub Pages
│  └─ ...
├─ output/firefox/                    ← Firefox 源码
│  ├─ manifest.json                   ← update_url 指向 GitHub Pages
│  └─ ...
├─ input/source.pem                   ← ⭐ Chrome 打包私钥（不入 git）
└─ scripts/
   ├─ release.py                      ← ⭐ 一键打包发版脚本（双端）
   └─ compute_ext_id.py               ← Chrome 扩展 ID 计算工具
```

### 关键参数

| 参数 | Chrome | Firefox |
|------|--------|---------|
| 扩展 ID | `inmachhhbcehlpklfjgenplmgffbiiaf` | `jira-template-manager@shugan` |
| 更新清单 | `update.xml` (XML 格式) | `updates.json` (JSON 格式) |
| 更新清单 URL | `https://shug666.github.io/JIRA_Efficiency_Assistant/update.xml` | `https://shug666.github.io/JIRA_Efficiency_Assistant/updates.json` |
| 检查频率 | 每 5 小时 | 约每天 1 次 |
| 签名要求 | 无（source.pem 自签） | **必须 AMO 签名** |
| 安装包格式 | `.crx` | `.xpi` |

---

## 二、Chrome 自动更新（已就绪，无需签名）

### 机制

```
Chrome 扩展（拖拽 .crx 安装）
    ↓ 每 5 小时
GET update.xml
    ↓ version > 本地
下载 codebase 指向的 .crx → 静默安装
```

Chrome 不需要任何签名，`source.pem` 自签的 crx 即可被认作合法扩展（前提是首次已拖拽安装）。

### 关键文件

- `input/source/manifest.json` 的 `update_url` → 指向 GitHub Pages 的 `update.xml`
- `docs/update.xml` → `appid` + `codebase` + `version`
- `docs/releases/jira-helper-chrome-X.Y.Z.crx` → 安装包

---

## 三、Firefox 自动更新（需 AMO 签名）

### ⚠️ 核心约束：必须签名

```
Firefox 安全策略：
  所有扩展必须经过 AMO 签名才能永久安装 + 自动更新

签名来源（二选一）：
  ① AMO 公开上架（过审核，公开可见）
  ② AMO 自托管签名 unlisted（过审核，但不公开列出）  ← 推荐

未签名的 xpi：
  只能用 about:debugging 临时加载（重启 Firefox 后失效，无自动更新）
```

### 签名流程（一次性配置）

1. **注册 AMO 开发者账号**
   - 访问 https://addons.mozilla.org/developers/
   - 注册并登录

2. **获取 API 密钥**
   - 访问 https://addons.mozilla.org/developers/addon/api/key/
   - 记录 `JWT Issuer` 和 `JWT Secret`

3. **安装 web-ext 工具**
   ```bash
   npm install -g web-ext
   ```

4. **配置环境变量**
   ```bash
   export AMO_JWT_ISSUER=user:19753416:500
   export AMO_JWT_SECRET=ae6b1e4ba8a6d0e80b47b209fb19922e4d02830eefbde088b6f8bf7142580ff7
   ```
   建议写入 `~/.bashrc` 或 `~/.zshrc` 持久化。

### 首次签名发布

```bash
# 签名并打包（需 AMO 密钥）
python3 scripts/release.py 3.3.0 --firefox --sign
```

或手动执行：
```bash
cd output/firefox
web-ext sign \
  --source-dir . \
  --api-key $AMO_JWT_ISSUER \
  --api-secret $AMO_JWT_SECRET \
  --artifacts-dir ../../docs/releases
```

签名成功后，`docs/releases/` 下会生成签名过的 `.xpi`。

### 自动更新机制

```
Firefox 扩展（已签名的 xpi 安装）
    ↓ 约每天 1 次
GET updates.json
    ↓ version > 本地 + 签名有效
下载 update_link 指向的 .xpi → 安装
```

`output/firefox/manifest.json` 的 `update_url` → 指向 GitHub Pages 的 `updates.json`。

---

## 四、日常发版流程

### 一键发版（两端同时）

```bash
# 前置：source.pem 在位，AMO 密钥已配置，两端都已 npm install
python3 scripts/release.py 3.4.0 --sign
```

脚本自动完成：
1. 改 Chrome + Firefox manifest + package.json 版本号
2. 两端各自 `npm run build`
3. Chrome: `source.pem` 打包 crx
4. Firefox: `web-ext sign` 签名打包 xpi
5. 更新 `docs/update.xml`（Chrome）
6. 更新 `docs/updates.json`（Firefox，含 SHA256 校验）
7. 打印 git 提交命令

### 只发 Chrome

```bash
python3 scripts/release.py 3.4.0 --chrome
```

### 只发 Firefox

```bash
python3 scripts/release.py 3.4.0 --firefox --sign
```

### 提交发布

```bash
git add docs/ input/source/manifest.json input/source/package.json output/firefox/manifest.json scripts/release.py
git commit -m "release: v3.4.0"
git push origin main
```

---

## 五、首次部署 GitHub Pages

1. 打开仓库 `Settings → Pages`
2. `Source` 选 `Deploy from a branch`
3. `Branch` 选 `main` / `(docs)`
4. 保存，等 1-2 分钟
5. 访问确认：
   - `https://shug666.github.io/JIRA_Efficiency_Assistant/` → 门户首页
   - `https://shug666.github.io/JIRA_Efficiency_Assistant/update.xml` → Chrome 清单
   - `https://shug666.github.io/JIRA_Efficiency_Assistant/updates.json` → Firefox 清单

---

## 六、验证自动更新

### Chrome

1. 拖拽安装当前版本 crx
2. 发新版 + push
3. `chrome://extensions/` → 点「更新」
4. 观察版本号变化

### Firefox

1. 安装签名过的 xpi
2. 发新版 + push
3. `about:addons` → 齿轮 → 「检查更新」
4. 观察版本号变化

---

## 七、常见排查

| 现象 | 原因 | 解决 |
|------|------|------|
| Chrome 更新后版本没变 | update.xml 缓存 | 强刷 update.xml 或等 Pages 生效 |
| Chrome 扩展 ID 不一致 | 用了不同的 pem | 必须用 `input/source.pem` |
| Firefox "无法安装，未验证" | xpi 未签名 | 用 `--sign` 参数 + AMO 密钥 |
| Firefox 更新不生效 | update_url 未配或未签名 | 确认 manifest.update_url + xpi 已签名 |
| codebase/update_link 404 | 文件名不匹配 | 检查 `docs/releases/` 文件名与清单一致 |
| GitHub Pages 返回 404 | 未开 Pages 或分支错 | Settings → Pages 确认 `main/docs` |

---

## 八、安全注意事项

### source.pem（Chrome 私钥）

- **绝对不入 git**（已加入 .gitignore）
- **绝不丢失**（丢失 = 失去 Chrome 扩展 ID = 所有用户无法更新）
- 备份到密码管理器 / 加密 U 盘

### AMO API 密钥（Firefox 签名）

- 不要硬编码到脚本，用环境变量
- 可在 AMO 后台随时重新生成

### ⚠️ 历史泄露处理

`input/source.pem` 曾被 git 跟踪过（现已移除）。如仓库为公开，需：
1. 用 `git filter-repo` 清除历史中的 pem
2. 或轮换密钥（生成新 pem → Chrome ID 变化 → 用户重装）

---

## 九、Chrome vs Firefox 更新机制对比

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
```

---

*本指南由 scripts/release.py 和 docs/ 目录共同维护。*
