## Historical Imports

This folder stores organization-scoped historical chat imports generated from raw exports.

### Command

```powershell
python manage.py import_historical_chats `
  --org-slug comfaguajira `
  --chats "C:\path\to\chats.jsonl" `
  --source-name comfaguajira_ws
```

### Outputs

- `normalized_conversations.jsonl`
  - Canonical conversation sessions with anonymized messages.
- `router_examples.jsonl`
  - Per-user-message examples for intent and route classification.
- `eval_examples.jsonl`
  - Real user prompts paired with the next human response.
- `kb_seed.json`
  - Topic-grouped seeds for knowledge base articles and playbooks.
- `report.json`
  - Aggregate counts by topic, stage, and route hint.

### Product intent

This pipeline is reusable across tenants.

- The ingestion and anonymization logic is platform-level.
- The resulting knowledge, evals, and topic distributions are organization-specific.
