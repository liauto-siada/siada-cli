# carapi-js-lib

封装车端接口，提供给AI卡片使用。

## 如何使用

### 在现代前端项目中使用 (ESM)

首先执行代码以下命令安装carapi-js-lib
```bash
# 假设您的项目和 carapi_js 在同一个父目录下
npm install /path/to/carapi_js
```

如果您正在使用 Vite、Webpack 或其他现代构建工具，可以直接在您的模块中导入。

```javascript
// 引入 callbackManager 单例
import callbackManager from 'carapi-js-lib';

const widgetId = 'widget-123';

// 添加监听器
callbackManager.addListener(widgetId, 'propertyA', (newValue) => {
    console.log(`propertyA 的新值为: ${newValue}`);
});

// 触发回调 (这通常由库内部逻辑调用)
callbackManager.onWidgetAgentCallback(widgetId, 'propertyA', '新值来了！');

// 检查监听器是否存在
console.log(
    '监听器存在吗?',
    callbackManager.hasListener(widgetId, 'propertyA') // -> true
);

// 移除监听器
callbackManager.removeListener(widgetId, 'propertyA');
```

### 在传统 HTML 页面中直接使用

您也可以直接在 HTML 文件中使用 `<script>` 标签引入库文件。

1.  首先，从 `dist` 文件夹中获取 `carapi-js-lib.umd.cjs` 文件并将其放置在您的项目中。

2.  在 HTML 文件中引入脚本。
参考test/testHtml.html

## 开发和构建

如果您想从源码构建此库：

1.  克隆仓库
2.  安装依赖: `npm install`
3.  运行构建: `npm run build`

构建产物将位于 `dist` 目录下。 