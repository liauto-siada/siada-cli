#!/bin/bash

# 使用pwd获取当前目录，如果获取不到则使用默认路径
CCA_AGENT_GRPC_WORKDIR=$(pwd)
if [ -z "$CCA_AGENT_GRPC_WORKDIR" ] || [ "$CCA_AGENT_GRPC_WORKDIR" = "/" ]; then
    CCA_AGENT_GRPC_WORKDIR="/chj/data/app/cockpit-create-agent/resources"
fi

echo "当前工作目录: $CCA_AGENT_GRPC_WORKDIR"

# 进入 mindui-components 目录并安装依赖
cd "${CCA_AGENT_GRPC_WORKDIR}/mindui-components" || { echo "无法进入 mindui-components 目录"; exit 1; }
npm install

# 进入 mindui-components/src/carapi_js 目录并构建
cd "${CCA_AGENT_GRPC_WORKDIR}/mindui-components/src/carapi_js" || { echo "无法进入 carapi_js 目录"; exit 1; }
npm run build
cd - || { echo "无法返回原目录"; exit 1; }

# 进入 mindui-components 目录并安装依赖
cd "${CCA_AGENT_GRPC_WORKDIR}/mindui-components" || { echo "无法进入 mindui-components 目录"; exit 1; }
npm install

mkdir -p "${CCA_AGENT_GRPC_WORKDIR}/crs_runtime"
# 将 node_modules 移动到 crs_runtime 目录
mv node_modules "${CCA_AGENT_GRPC_WORKDIR}/crs_runtime/" || { echo "移动 node_modules 失败"; exit 1; }

# 创建 carapi-js-lib 的软链接
cd "${CCA_AGENT_GRPC_WORKDIR}/crs_runtime/node_modules" || { echo "无法进入 node_modules 目录"; exit 1; }
ln -snf ../../mindui-components/src/carapi_js carapi-js-lib || { echo "创建软链接失败"; exit 1; }

echo "✅ 更新完成！"
