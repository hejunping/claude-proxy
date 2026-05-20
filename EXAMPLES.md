# Claude CLI Proxy 使用示例

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

## 多轮对话

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
