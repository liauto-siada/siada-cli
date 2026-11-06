# Chrome 本机自动连接

安装 Siada CLI 后，安装并启动浏览器组件：

```bash
siada-browser setup
```

在 `chrome://extensions` 中加载 setup 输出的扩展目录，再打开 Siada 侧栏。
扩展会获取正在运行的本机 proxy 的 token，保存到连接设置并自动连接。
随后沿用现有 ACP 握手启动配置的 CLI，并显示连接失败信息。

CLI 未登录时，侧栏显示与 CLI 对应的 API Key、Free Trial 两项登录。
proxy 运行 `siada-cli --browser-login` 并通过获授权的本机连接传递登录消息。
在 Chrome 中完成向导，CLI 校验并保存配置，侧栏在登录后自动连接。
API Key 输入隐藏显示，不保存到 Chrome 存储；关闭向导会结束对应登录子进程。

展开顶部连接设置，点击「重新登录 / 切换模型服务」可更换登录方式。
取消会保留当前配置并恢复连接，配置成功后自动重新连接。

本机 proxy 不可用时，侧栏中央显示 Chrome ACP 图标和可复制的安装命令，
每 5 秒重试检测。底部点击「已安装 / 其它设备存在 Siada CLI」可打开连接界面，
填写地址和 token。开源安装脚本默认绑定回环地址；Chrome 引导提供 GitHub Pages 站点上的
Linux / macOS Shell 和 Windows PowerShell 命令。测试版命令选择对应的 TestPyPI
wheel 和浏览器版本，依赖从 PyPI 获取。已有安装可以运行：

```bash
siada-browser start
```

检测使用设置中的本机服务地址，默认端口为 9315。
远程连接和旧版 proxy 继续支持手动填写 token。
已有 proxy 需要更新并重启才能提供自动发现接口；
更新已解压扩展文件后，需要在 Chrome 中重新加载扩展。

token 获取接口仅允许 setup 安装的扩展通过本机明文回环连接访问。
CLI 根据扩展 manifest 公钥或加载目录计算允许的扩展 ID。
单独加载其他目录中的扩展时，可在启动 proxy 时指定该扩展 ID：

```bash
SIADA_BROWSER_EXTENSION_IDS=<扩展ID> siada-browser restart
```

普通网页和远程设备无法使用此接口读取 token。