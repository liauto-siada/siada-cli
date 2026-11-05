# 浏览器安装

浏览器安装器从 GitHub Releases 下载与已安装 CLI 版本对应的平台 ZIP。
ZIP 包含 Node.js 24.13.0、代理服务、锁定的生产依赖、网页客户端、
Chrome 扩展和许可证说明。Python wheel 包含终端 UI 和浏览器安装器。

安装已发布版本的 Siada CLI 后运行：

```bash
siada-browser setup
```

安装器先验证 manifest、SHA-256、许可证和运行时，再替换旧安装。
下载或验证失败时保留旧安装；连接配置也会保留。

打开 `chrome://extensions`，启用开发者模式，加载
`~/.siada-cli/browser/extension`。本机连接会自动获取 token；
远程连接需要配置服务地址和 token。

```bash
siada-browser status
siada-browser stop
siada-browser start
```

更新已发布的安装：

```bash
uv tool upgrade siada-cli
siada-browser setup
```

更新后在 Chrome 中重新加载扩展。只使用终端的用户可以自行安装
Node.js 24 LTS；CLI 启动不会下载或安装工具链。

从源码开发：

```bash
cd chrome-acp
bun install --frozen-lockfile
bun run test
bun run build
cd ..
poetry run siada-browser setup chrome-acp
```

源码安装使用代理服务的 npm lockfile 安装生产依赖。
公开浏览器工作流生成 macOS、Linux 和 Windows 平台 ZIP。