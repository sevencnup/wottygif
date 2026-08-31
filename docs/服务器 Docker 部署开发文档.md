# WottyGIF 服务器 Docker 部署开发文档

## 目标

使用 Ops Control 在已配置的 Docker 服务器上创建独立的 `wottygif` Compose 项目，拉取 WottyGIF 镜像并通过 `gif.wotty.app` 提供访问。部署不得影响服务器上已有项目。

## 固定部署参数

- Compose 项目：`wottygif`
- 服务/容器：`wottygif`
- 镜像：`ghcr.io/sevencnup/wottygif:main`
- 容器端口：`8699:8699`
- 持久化卷：`wottygif-data:/app/data/results`
- 访问域名：`gif.wotty.app`
- 反向代理上游：服务器本机 `8699` 端口

## 执行步骤

1. 使用 Ops Control 发现服务器 Docker 状态，确认 `8699` 未被现有容器占用。
2. 创建只包含 WottyGIF 的 Compose 项目。创建动作必须显式拉取镜像，然后启动项目；禁止使用特权容器、宿主网络、宿主 PID/IPC 或 Docker Socket。
3. 确认 `wottygif` 容器处于运行且健康状态。
4. 为 `gif.wotty.app` 写入受控 Nginx 反向代理，执行 `nginx -t` 后再 reload。
5. 检查服务器本机 HTTP、域名 HTTP/HTTPS 和 `/api/health`。
6. 若镜像仓库需要认证，只记录脱敏错误并停止，不读取或输出服务器凭据。

## 回滚/停止约束

部署失败时只允许查看日志、停止或修正后重新创建；不得删除容器、镜像、卷、网络，不得执行 `compose down`、prune 或任意清理命令。

## 验收标准

- `wottygif` 容器运行并通过镜像内健康检查。
- `http://服务器IP:8699/api/health` 返回成功。
- `http://gif.wotty.app` 能访问 WottyGIF 页面或由 Cloudflare 正确转发。
- HTTPS 是否可用取决于 Cloudflare SSL 模式及源站证书；若出现 526，需要配置有效源站证书或将 Cloudflare 回源模式调整为允许 HTTP。
