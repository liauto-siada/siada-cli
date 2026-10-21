# 浏览器安装与发布

每个平台发布一个 ZIP，包含 Node.js 24.13.0 及许可证、代理服务及锁定的
生产依赖、网页客户端、Chrome 扩展和第三方许可声明。Python wheel 包含
终端 UI bundle 和浏览器安装器，不包含浏览器二进制产物。

当前正式版本为 [1.7.37](https://github.com/liauto-siada/siada-cli/releases/tag/v1.7.37)。平台包随 CLI 版本发布在 GitHub Releases。
构建会检查随包运行时和代理；安装后请重新加载扩展并检查连接。

## 安装已发布版本

```bash
uv tool install --force --python python3.12 --with pip --default-index https://pypi.org/simple "siada-cli==1.7.37"
uv tool update-shell
siada-browser setup
```

安装器从当前 CLI 版本对应的 GitHub Release `v<版本>` 获取
`browser-manifest.json`，选择操作系统与架构，检查 ZIP 的 SHA-256。
它会检查许可证，在暂存目录运行 Node 和代理 CLI 检查，再替换安装文件，
保留连接配置。下载或校验失败时保留原安装。

打开 `chrome://extensions`，开启开发者模式，加载
`~/.siada-cli/browser/extension`。扩展自动发现本机 token，
默认本地地址为 `ws://localhost:9315/ws`。远程连接需手动填写地址和 token。
在 Chrome 登录向导中选择 API Key 或 Free Trial。

Linux/macOS 一键安装：

```bash
curl -fsSL https://liauto-siada.github.io/siada-cli/scripts/install-browser.sh | SIADA_VERSION=1.7.37 sh
```

Windows PowerShell 一键安装：

```powershell
& ([scriptblock]::Create((Invoke-WebRequest -UseBasicParsing 'https://liauto-siada.github.io/siada-cli/scripts/install-browser.ps1').Content)) -Version '1.7.37'
```

```bash
siada-browser status
siada-browser stop
siada-browser start
```

终端 UI 和代理服务共用安装的 Node。仅使用终端时，可自行安装 Node.js
24 LTS；启动器不会自动下载运行时。

## 升级

```bash
uv tool upgrade siada-cli
siada-browser setup
```

setup 后在 Chrome 中重新加载扩展。扩展目录保持固定。浏览器 ZIP 版本
与 CLI 一致，扩展和代理组件版本作为内部信息保留。

## 源码开发

准备 Poetry、带 npm 的 Node.js 24 LTS 和 Bun，先用 Poetry 安装 Python
工程，再构建浏览器组件：

```bash
cd chrome-acp
bun install --frozen-lockfile
bun run test
bun run build
cd ..
poetry run siada-browser setup chrome-acp
```

源码安装使用已有 Node，并通过 npm 从代理服务的已提交锁文件安装生产依赖。

## 打包与发布

构建完成后执行：

```bash
node scripts/package-browser.mjs pack
```

也可使用 `just pack` 一起构建、打包。产物写入 `chrome-acp/release/`。
打包器支持在对应构建主机生成 macOS ARM64/x64、Linux ARM64/x64 和
Windows x64 包。支持配置不代表各平台已经通过验收。

仓库根目录的 `browser-release.yml` workflow 接受已有 tag，以及默认
为 false 的 `publish` 参数。它核对 tag 与 CLI 版本，运行组件测试、构建、
平台打包，再合并 manifest 并校验哈希。显式设置 `publish=true` 才发布；
流程不发布 npm 包，也不推送 tag。

候选包可放在 HTTPS 目录中，同目录提供 manifest 和对应 ZIP：

```bash
siada-browser setup --base-url https://example.com/candidate
```

发布前应在每个支持平台验证干净安装和 Chrome 连接。最终将 manifest
及平台 ZIP 一起上传到对应 CLI 版本的 GitHub Release。