#!/bin/bash

# 设置工作目录（请根据实际情况替换为你的实际路径）
#CCA_AGENT_GRPC_WORKDIR="/home/lixiang/cockpit-create-agent-master/cockpit-create-agent-master/agent/app/src/main/resources"
CCA_AGENT_GRPC_WORKDIR="/home/lixiang/cockpit-create-agent/agent/app/src/main/resources"

rm -rf ${CCA_AGENT_GRPC_WORKDIR}/crs_runtime/node_modules

# 进入 mindui-components 目录并安装依赖
cd "${CCA_AGENT_GRPC_WORKDIR}/mindui-components" || { echo "无法进入 mindui-components 目录"; exit 1; }
npm install

# 将 node_modules 移动到 crs_runtime 目录
mv node_modules "${CCA_AGENT_GRPC_WORKDIR}/crs_runtime/" || { echo "移动 node_modules 失败"; exit 1; }

# 创建 carapi-js-lib 的软链接
cd "${CCA_AGENT_GRPC_WORKDIR}/crs_runtime/node_modules" || { echo "无法进入 node_modules 目录"; exit 1; }
ln -snf ../../mindui-components/src/carapi_js carapi-js-lib || { echo "创建软链接失败"; exit 1; }

echo "✅ 更新完成！"

# 在 agent 目录下运行 mvn 命令
cd ${CCA_AGENT_GRPC_WORKDIR}/../../../../agent || { echo "无法进入 agent 目录"; exit 1; }
mvn clean install -DskipTests

# 在 grpc_server 目录下运行 mvn 命令
cd ${CCA_AGENT_GRPC_WORKDIR}/../../../../grpc_server || { echo "无法进入 grpc_server 目录"; exit 1; }
mvn clean install -DskipTests
