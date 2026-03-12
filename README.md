# PrepSignal

Interview post collector + AI knowledge layer.

## 1. Collection (Chrome extension)

- Install extension from `extension/`
- Run backend: `./run_backend.sh`
- Open Chrome → extension auto-collects from forum-145

## 2. Knowledge layer (AI parsing)

Parse raw posts into structured knowledge.

### 默认：Cursor Agent CLI

使用 Cursor 的 `agent` 命令（无需 API key，登录即可）：

```bash
# 首次安装：https://cursor.com/docs/cli/using
agent login   # 一次性登录

./run_knowledge_worker.sh --limit 20
```

- `agent` 不在 PATH 时：设置 `CURSOR_AGENT_PATH`
- 默认模型：`composer-1.5`，mode：`ask`（无需 stream，直接拿完整输出）
- 覆盖：`CURSOR_AGENT_MODEL=claude-sonnet CURSOR_AGENT_MODE=agent ./run_knowledge_worker.sh --limit 20`

### 可选：OpenAI / Anthropic API

```bash
export OPENAI_API_KEY=sk-...   # 或 ANTHROPIC_API_KEY
./run_knowledge_worker.sh --api --limit 20
```

- **OpenAI**：`OPENAI_API_KEY`，model `gpt-4o-mini`
- **Anthropic**：`ANTHROPIC_API_KEY`，model `claude-3-5-haiku-20241022`
- 指定模型：`KNOWLEDGE_MODEL=gpt-4o ./run_knowledge_worker.sh --api`

### Endpoints

- `GET /posts` – raw posts
- `GET /interpreted` – AI-parsed knowledge base
