# Memory Bank API 移行仕様書

## 概要

Vertex AI Agent EngineのAPIがクライアントベースの新設計に移行したため、`memory_bank_storage.py`を更新。

---

## 変更内容

### 旧API（非推奨）
```python
import vertexai
from vertexai import agent_engines

vertexai.init(project=PROJECT, location=LOCATION)
agent_engines.create(display_name="...", config={...})
```

### 新API（クライアントベース）
```python
import vertexai

client = vertexai.Client(project=PROJECT, location=LOCATION)
client.agent_engines.create(
    agent=None,  # Memory Bank専用エンジンの場合
    config={
        "display_name": "shadow-director-memory-bank",
        "context_spec": {
            "memory_bank_config": {}
        }
    }
)
```

---

## Memory Bank API一覧

| 旧API | 新API |
|:------|:------|
| `agent_engines.create()` | `client.agent_engines.create()` |
| `agent_engines.list()` | `client.agent_engines.list()` |
| `agent_engines.get()` | `client.agent_engines.get(name=...)` |
| N/A | `client.agent_engines.memories.generate()` |
| N/A | `client.agent_engines.memories.retrieve()` |

---

## 環境変数

| 変数名 | 説明 |
|:-------|:-----|
| `USE_MEMORY_BANK` | `true`でMemory Bank有効化 |
| `GOOGLE_CLOUD_AGENT_ENGINE_ID` | 既存Agent Engine IDを指定 |
| `MEMORY_BANK_LOCATION` | リージョン（デフォルト: us-central1） |

---

## 参照ドキュメント

- [Agent Engine 移行ガイド](https://cloud.google.com/vertex-ai/generative-ai/docs/deprecations/agent-engine-migration)
