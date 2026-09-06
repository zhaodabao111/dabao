# 语音约碰面地点

当前阶段包含项目骨架、后端健康检查和前端基础页面。录音、语音识别、
信息提取、地点搜索、推荐语和语音合成功能尚未实现。

## 环境要求

- Python 3.12（当前本地运行时为 3.12.14）
- Node.js 22.12 或更高的 22.x 版本

## 启动后端

在 `project` 目录执行：

```bash
uv venv --python /Users/didi/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 .venv
uv pip install --python .venv/bin/python -r backend/requirements.txt
cp backend/.env.example backend/.env
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8003
```

外部服务密钥可以保持为空，健康检查不读取或调用任何外部服务。

## 启动前端

打开另一个终端，在 `project/frontend` 目录执行：

```bash
npm install
npm run dev
```

浏览器访问 <http://localhost:5175>。后端已启动时，页面会显示
“后端服务连接正常”和本次健康检查的 `request_id`。

## 验证健康检查

直接访问 <http://localhost:8003/health>，预期 HTTP 200：

```json
{
  "request_id": "req_每次请求生成的编号",
  "data": {
    "status": "ok"
  }
}
```

FastAPI 文档位于 <http://localhost:8003/docs>。展开 `GET /health`，点击
“Try it out”与“Execute”，应看到状态码 200 和相同结构的响应。

## 运行后端测试

在 `project` 目录执行：

```bash
.venv/bin/python -m pytest backend/tests -v
```

测试覆盖健康检查响应结构，以及只允许约定前端来源的 CORS 预检响应。
