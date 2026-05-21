# Claude CLI Proxy

将本机 Claude CLI 包装成标准的 **Anthropic Messages API**，任何兼容 Anthropic SDK（`anthropic`、`@anthropic-ai/sdk`）的客户端都能直连。

特性：

- 标准 `/v1/messages` 接口（流式 / 非流式）
- 标准 Anthropic SSE 事件序列（`message_start` / `content_block_start` / `content_block_delta` / `content_block_stop` / `message_delta` / `message_stop`）
- `/v1/models` 列表接口（Anthropic 格式）
- CORS 全开，浏览器可直连
- 模型别名（opus / sonnet / haiku → 完整模型 ID）
- **扩展**：`X-Session-ID` header 复用 Claude CLI 原生 session，多轮对话无需重发历史

## 启动服务

```bash
pip install -r requirements.txt
export PROXY_API_KEYS="sk-your-secret-key"   # 推荐显式设置
python main.py
```

服务默认运行在 `http://localhost:9090`。

> 若未设置 `PROXY_API_KEYS`，代理会在启动时**自动生成**一个一次性 key 并打印到日志，方便快速试用：
>
> ```
> [WARNING] PROXY_API_KEYS not set. Generated a temporary key for this process:
>     sk-proxy-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
> ```
>
> 进程重启后这个 key 会变。生产环境请显式配置 `PROXY_API_KEYS`。

---

## 鉴权（所有接口必须）

所有路由（含 `/health`、`/v1/models`、`/v1/messages`）都要求 API key。支持两种 header（任选其一）：

| Header | 说明 |
|--------|------|
| `x-api-key: <key>` | Anthropic 原生风格 |
| `Authorization: Bearer <key>` | 通用 / OpenAI 风格 |

未带 key 或 key 错误时返回 `401`：

```json
{
  "type": "error",
  "error": {
    "type": "authentication_error",
    "message": "Invalid API key."
  }
}
```

> CORS 预检 `OPTIONS` 请求不需要鉴权。

---

## 基础请求

> 下面所有示例假定 `export PROXY_API_KEY=sk-your-secret-key`，并以 `x-api-key` header 携带；用 `Authorization: Bearer $PROXY_API_KEY` 也等价。

### 非流式

```bash
curl http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: $PROXY_API_KEY" \
  -d '{
    "model": "sonnet",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "你好"}
    ]
  }'
```

响应：

```json
{
  "id": "msg_8f2c8e6b0d79a1b3c4d5e6f7",
  "type": "message",
  "role": "assistant",
  "content": [
    {"type": "text", "text": "你好！有什么我可以帮你的吗？"}
  ],
  "model": "sonnet",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 5785,
    "output_tokens": 12
  }
}
```

### 流式

```bash
curl http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: $PROXY_API_KEY" \
  -d '{
    "model": "sonnet",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "从1数到5"}
    ],
    "stream": true
  }'
```

输出（标准 Anthropic SSE）：

```
event: message_start
data: {"type":"message_start","message":{"id":"msg_xxx","type":"message","role":"assistant","content":[],"model":"sonnet","stop_reason":null,"stop_sequence":null,"usage":{"input_tokens":0,"output_tokens":0}}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"1, 2, 3, 4, 5"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"input_tokens":12,"output_tokens":9}}

event: message_stop
data: {"type":"message_stop"}
```

---

## 带 system 提示

`system` 既支持字符串，也支持 text block 数组。

```bash
curl http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: $PROXY_API_KEY" \
  -d '{
    "model": "sonnet",
    "max_tokens": 1024,
    "system": "你是一个专业的翻译助手，只输出翻译结果",
    "messages": [
      {"role": "user", "content": "翻译成英文：今天天气真好"}
    ]
  }'
```

或 block 数组形式：

```json
{
  "system": [
    {"type": "text", "text": "你是一个专业的翻译助手"},
    {"type": "text", "text": "只输出翻译结果"}
  ]
}
```

---

## 多轮对话

### 方式 1：完整历史

```bash
curl http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: $PROXY_API_KEY" \
  -d '{
    "model": "sonnet",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "我叫小明"},
      {"role": "assistant", "content": "你好小明！"},
      {"role": "user", "content": "我叫什么名字？"}
    ]
  }'
```

### 方式 2：Session 持久化（本代理扩展）

通过 `X-Session-ID` header 复用 CLI 原生 session，不必重发历史。

第一次请求 — 不带 header，响应 header 自动返回一个新生成的 `X-Session-ID`（UUID）：

```bash
curl -v http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: $PROXY_API_KEY" \
  -d '{
    "model": "sonnet",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "我叫小明"}]
  }'
# 响应 header: X-Session-ID: 8f2c8e6b-0d79-4a1b-8c3d-4e5f6789abcd
```

后续请求带上拿到的 session UUID，只发新消息：

```bash
curl http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: $PROXY_API_KEY" \
  -H "X-Session-ID: 8f2c8e6b-0d79-4a1b-8c3d-4e5f6789abcd" \
  -d '{
    "model": "sonnet",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "我叫什么名字？"}]
  }'
```

Session 优势：
- Token 消耗更低（不重发历史）
- 对话质量更好（CLI 原生多轮上下文）
- 支持流式和非流式

> 注：
> - Session 是本代理对 Anthropic API 的扩展，不属于 Anthropic 官方协议
> - `X-Session-ID` 必须是合法 UUID（Claude CLI 的 `--session-id` 要求）。建议第一次让代理自动生成
> - 不带该 header 时每次请求都是独立 session，行为基本等同标准 Messages API

---

## 多模态 content（仅 text 块生效）

`content` 既支持纯字符串，也支持 Anthropic 风格的 block 数组：

```bash
curl http://localhost:9090/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: $PROXY_API_KEY" \
  -d '{
    "model": "sonnet",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": [
        {"type": "text", "text": "你好"},
        {"type": "text", "text": "请用一句话自我介绍"}
      ]}
    ]
  }'
```

`image` block 会被忽略 —— Claude CLI 的 `-p` 模式不接受图像输入。`tool_use` / `tool_result` block 的文本会被串联。

---

## Anthropic Python SDK

```python
import os
from anthropic import Anthropic

client = Anthropic(
    base_url="http://localhost:9090",
    api_key=os.environ["PROXY_API_KEY"],  # 会自动以 x-api-key header 发送
)

resp = client.messages.create(
    model="sonnet",
    max_tokens=1024,
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.content[0].text)

with client.messages.stream(
    model="sonnet",
    max_tokens=1024,
    messages=[{"role": "user", "content": "讲个笑话"}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

---

## 可用模型

```bash
curl http://localhost:9090/v1/models \
  -H "x-api-key: $PROXY_API_KEY"
```

响应：

```json
{
  "data": [
    {"type": "model", "id": "claude-opus-4-7", "display_name": "Claude Opus 4 7", "created_at": "2025-01-01T00:00:00Z"},
    {"type": "model", "id": "claude-sonnet-4-6", "display_name": "Claude Sonnet 4 6", "created_at": "2025-01-01T00:00:00Z"},
    {"type": "model", "id": "claude-haiku-4-5", "display_name": "Claude Haiku 4 5", "created_at": "2025-01-01T00:00:00Z"}
  ],
  "has_more": false
}
```

可用别名（自动展开为对应完整 ID）：

| 别名 | 完整 ID |
|------|---------|
| `opus` / `claude-opus` | claude-opus-4-7 |
| `sonnet` / `claude-sonnet` | claude-sonnet-4-6 |
| `haiku` / `claude-haiku` | claude-haiku-4-5 |

---

## 错误响应

所有错误使用 Anthropic 标准结构。

非流式：

```json
{
  "type": "error",
  "error": {
    "type": "api_error",
    "message": "Claude CLI not found in PATH"
  }
}
```

流式：错误以 `event: error` 形式下发，随后流结束。

---

## 健康检查

```bash
curl http://localhost:9090/health \
  -H "x-api-key: $PROXY_API_KEY"
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PROXY_API_KEYS` | 启动时随机生成 | 鉴权 key，多个用逗号分隔；也兼容 `PROXY_API_KEY`（单数） |
| `CLAUDE_CLI_PATH` | `claude` | Claude CLI 路径 |
| `PROXY_PORT` | `9090` | 服务端口 |
| `REQUEST_TIMEOUT` | `300` | 请求超时（秒） |

---

## 已知限制

- **`max_tokens`**：Anthropic 协议必填，但 Claude CLI 本身没有暴露 token 上限参数（仅有 `--max-budget-usd`），所以该字段会被代理接收并忽略
- **`temperature` / `top_p` / `top_k` / `stop_sequences`**：同上，CLI `-p` 模式未透出对应开关，目前由代理静默接受
- **`tools` / `tool_choice`**：Claude CLI 已经在内部驱动工具调用，外部协议层的 tool calling 暂不映射
- **图像 `image` block**：CLI `-p` 模式不接受图像输入，会被忽略
