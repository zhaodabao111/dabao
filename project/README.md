# 语音约碰面地点

当前阶段包含项目骨架、后端健康检查、前端本地录音/试听/临时下载，
以及可独立测试的后端录音上传、ASR 和信息提取接口。前端尚未调用这些后端接口；
地点搜索、推荐语和语音合成功能尚未实现。

## 环境要求

- Python 3.12（当前本地运行时为 3.12.14）
- Node.js 22.12 或更高的 22.x 版本
- FFmpeg（后端只使用其中的 `ffprobe` 探测音频，不执行转码）

macOS 使用 Homebrew 安装 FFmpeg：

```bash
brew install ffmpeg
ffprobe -version
```

## 启动后端

在 `project` 目录执行：

```bash
uv venv --python /Users/didi/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 .venv
uv pip install --python .venv/bin/python -r backend/requirements.txt
cp backend/.env.example backend/.env
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8003
```

外部服务密钥可以保持为空，健康检查不读取或调用任何外部服务。
`POST /upload` 需要 `ffprobe` 在 `PATH` 中；它会核验真实 WebM 容器、
Opus 编码和音频时长，而不是相信扩展名或上传的 Content-Type。
`POST /asr` 还需要填写北京地域的 `BAILIAN_API_KEY`，并将
`BAILIAN_ASR_URL` 中的 `{WorkspaceId}` 替换为真实业务空间 ID；默认不配置
密钥时，健康检查和上传接口仍可启动，但 ASR 会返回未配置错误。

## 启动前端

打开另一个终端，在 `project/frontend` 目录执行：

```bash
npm install
npm run dev
```

浏览器访问 <http://localhost:5175>。后端已启动时，页面会显示
“后端服务连接正常”和本次健康检查的 `request_id`。

页面会先用 `MediaRecorder.isTypeSupported` 检查 WebM/Opus 支持。按住录音
按钮开始，松开结束，按 Esc 可取消。有效录音必须为1—60秒且不超过5 MiB；
完成后可直接试听或临时下载 WebM 文件。本阶段不会向后端上传录音。

## 验证录音上传

打开 <http://localhost:8003/docs>，展开 `POST /upload`，点击“Try it out”，
在 `file` 中选择前端下载的 `.webm` 文件后执行。有效文件预期 HTTP 200：

```json
{
  "request_id": "req_每次请求生成的编号",
  "data": {
    "audio_id": "rec_后端生成的临时编号"
  }
}
```

录音保存在 `backend/storage/recordings/`。每条录音包含以同一个 `audio_id`
命名的 `.webm` 文件和 `.json` 元数据；元数据记录创建时间、大小、真实格式、
编码和时长。存储路径不会通过接口返回。元数据读取方法会按配置的24小时
有效期检查，但读取录音的业务接口和启动清理尚未在本阶段实现。

## 验证语音识别

先在 `POST /upload` 上传真实 `.webm`，记录返回的 `audio_id`。然后在
<http://localhost:8003/docs> 展开 `POST /asr`，请求体填写：

```json
{
  "audio_id": "rec_上传接口返回的编号"
}
```

成功调用百炼后预期 HTTP 200：

```json
{
  "request_id": "req_每次请求生成的编号",
  "data": {
    "text": "实际语音识别出的原话"
  }
}
```

本接口会读取已保存文件，重新检查编号、元数据、文件存在性、24小时有效期
和文件大小；再按百炼要求构造 `data:audio/webm;base64,...`。Base64 编码大小
由 `ASR_MAX_BASE64_BYTES` 控制，默认10MiB。服务商响应中的空文本、异常结构、
HTTP 错误和超时都会转换为统一错误结构；不会返回固定占位文本，也不会记录
API Key 或 Base64 音频内容。

真实 ASR 测试需要北京地域 API Key 和正确的 Workspace ID，会产生百炼调用费用。
后端 Mock 测试只替换服务商调用，不访问百炼、不产生费用。

## 验证信息提取 `/extract`

本轮新增的 `POST /extract` 只接收 JSON，不接入前端。请求体为：

```json
{
  "text": "我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。",
  "city": "杭州"
}
```

在 <http://localhost:8003/docs> 展开 `POST /extract`，点击 “Try it out”，
粘贴上面的请求后执行。真实调用需要在 `backend/.env` 填写
`DEEPSEEK_API_KEY`，会产生 DeepSeek 调用费用；未配置时预期返回 HTTP 503，
不会调用外部服务。自动化测试通过 Mock 替换 DeepSeek 调用，不产生费用，
但本轮没有由开发者自动执行。

DeepSeek 返回的模型原始 JSON 只在后端内部处理，包含诊断字段，例如：

```json
{
  "party_count": 2,
  "city_a": "杭州",
  "address_a": "杭州东站",
  "city_b": "杭州",
  "address_b": "西湖龙翔桥地铁站",
  "category": "喝咖啡",
  "incomplete_reason": null,
  "address_a_ambiguous": false,
  "address_b_ambiguous": false
}
```

正常情况下（HTTP 200）只返回约定的五个业务字段，模型内部的
`party_count`、`incomplete_reason` 和地址含糊诊断字段不会透传：

```json
{
  "request_id": "req_...",
  "data": {
    "city_a": "杭州",
    "address_a": "杭州东站",
    "city_b": "杭州",
    "address_b": "西湖龙翔桥地铁站",
    "category": "咖啡店"
  }
}
```

可以直接在 `/docs` 输入下面几组请求验证业务分支：

1. 页面城市回退和类别默认：

```json
{
  "text": "我在东站，朋友在西湖边。",
  "city": "杭州"
}
```

未口述城市时，模型应使用页面城市；未说类别时，最终类别为“咖啡店”。

2. 地址缺失：

```json
{
  "text": "我在杭州东站，朋友也在杭州，想喝咖啡。",
  "city": "杭州"
}
```

预期 HTTP 422，`error.code` 为 `EXTRACT_INCOMPLETE`。

3. 人数不符：

```json
{
  "text": "我和朋友都在杭州东站，帮我们找咖啡店。",
  "city": "杭州"
}
```

预期 HTTP 422，`error.code` 为 `EXTRACT_INCOMPLETE`。

4. 含糊地址：

```json
{
  "text": "我在我家，朋友在杭州东站。",
  "city": "杭州"
}
```

预期 HTTP 422，`error.code` 为 `EXTRACT_INCOMPLETE`，要求改成具体地点。

5. 跨城：

```json
{
  "text": "我在杭州东站，朋友在上海虹桥站。",
  "city": "杭州"
}
```

预期 HTTP 422，`error.code` 为 `EXTRACT_CROSS_CITY`。

模型返回非法 JSON、字段缺失或字段类型不符时，先在 Pydantic 结构校验阶段失败，
预期 HTTP 502、`error.code` 为 `EXTRACT_MODEL_OUTPUT_INVALID`；这与用户信息不完整
导致的 HTTP 422 不同。DeepSeek 超时返回 HTTP 504、`EXTRACT_TIMEOUT`，服务异常
返回 HTTP 502、`EXTRACT_PROVIDER_ERROR`。所有错误仍遵守统一的 `request_id` 和
`error` 响应结构。

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

测试代码覆盖健康检查、CORS、上传分支，以及 ASR 的成功、编号不存在、未配置、
Base64 超限、空结果和超时分支，还有信息提取的成功、城市回退、类别归一化、
缺失地址、人数不符、含糊地址、跨城、模型格式异常和超时分支。外部服务调用
在测试中使用 Mock，不产生费用；Mock 测试不能替代真实鉴权、真实识别/提取和
网络超时验收。
