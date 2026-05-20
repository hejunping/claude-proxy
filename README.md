# Claude CLI Proxy

OpenAI 兼容的 API 代理，将 Claude CLI 暴露为标准 API 服务。支持流式输出、Session 持久化、模型映射。

任何兼容 OpenAI SDK 的客户端（Cursor、Continue、自定义应用）都可以直接对接。

## 启动服务

```bash
pip install -r requirements.txt
python main.py
```

服务默认运行在 `http://localhost:9090`

---

## 基础请求

### 非流式请求

```bash
curl http://localhost:9090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sonnet",
    "messages": [
      {"role": "user", "content": "你好"}
    ]
  }'
```

响应：

```json
{
  "id": "chatcmpl-d73b8e6b0d79",
  "object": "chat.completion",
  "created": 1779264887,
  "model": "sonnet",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好！有什么我可以帮你的吗？"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 5785,
    "completion_tokens": 12,
    "total_tokens": 5797
  }
}
```

### 流式请求

```bash
curl http://localhost:9090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sonnet",
    "messages": [
      {"role": "user", "content": "从1数到5"}
    ],
    "stream": true
  }'
```

响应（SSE 格式）：

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1779264899,"model":"sonnet","choices":[{"index":0,"delta":{"role":"assistant","content":null},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1779264899,"model":"sonnet","choices":[{"index":0,"delta":{"role":null,"content":"1, 2, 3, 4, 5"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1779264899,"model":"sonnet","choices":[{"index":0,"delta":{"role":null,"content":null},"finish_reason":"stop"}]}

data: [DONE]
```

---

## 带 System Prompt

```bash
curl http://localhost:9090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sonnet",
    "messages": [
      {"role": "system", "content": "你是一个专业的翻译助手，只输出翻译结果"},
      {"role": "user", "content": "翻译成英文：今天天气真好"}
    ]
  }'
```

## 多轮对话（无 Session）

```bash
curl http://localhost:9090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sonnet",
    "messages": [
      {"role": "user", "content": "我叫小明"},
      {"role": "assistant", "content": "你好小明！"},
      {"role": "user", "content": "我叫什么名字？"}
    ]
  }'
```

## 多轮对话（Session 持久化）

通过 `X-Session-ID` header 保持会话上下文，无需每次发送完整历史。

第一次请求 — 自动创建 session，响应 header 返回 `X-Session-ID`：

```bash
curl -v http://localhost:9090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sonnet",
    "messages": [{"role": "user", "content": "我叫小明"}]
  }'
# 响应 header: X-Session-ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

后续请求 — 带上 session ID，只需发最新消息：

```bash
curl http://localhost:9090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
  -d '{
    "model": "sonnet",
    "messages": [{"role": "user", "content": "我叫什么名字？"}]
  }'
# Claude 会回答 "小明"
```

Session 优势：
- Token 消耗更低（不重发历史）
- 对话质量更好（CLI 原生多轮上下文）
- 支持流式和非流式

## 指定 max_tokens

```bash
curl http://localhost:9090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "opus",
    "messages": [
      {"role": "user", "content": "写一首短诗"}
    ],
    "max_tokens": 100
  }'
```

---

## Python OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:9090/v1",
    api_key="not-needed",
)

# 非流式
response = client.chat.completions.create(
    model="sonnet",
    messages=[{"role": "user", "content": "你好"}],
)
print(response.choices[0].message.content)

# 流式
stream = client.chat.completions.create(
    model="sonnet",
    messages=[{"role": "user", "content": "讲个笑话"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

---

## 可用模型

```bash
curl http://localhost:9090/v1/models
```

| 模型名称 | 映射到 |
|---------|--------|
| `opus` / `gpt-4` / `claude-opus` | claude-opus-4-7 |
| `sonnet` / `gpt-4o` / `claude-sonnet` | claude-sonnet-4-6 |
| `haiku` / `gpt-3.5-turbo` / `claude-haiku` | claude-haiku-4-5 |

也可以直接使用完整模型 ID，如 `claude-opus-4-7`。

---

## 健康检查

```bash
curl http://localhost:9090/health
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CLAUDE_CLI_PATH` | `claude` | Claude CLI 路径 |
| `PROXY_PORT` | `9090` | 服务端口 |
| `REQUEST_TIMEOUT` | `300` | 请求超时（秒） |
