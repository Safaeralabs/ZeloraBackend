"""
Create sales_agent_logs and ai_agents tables using RunSQL.

These tables were missing from the original syncdb because the models were added
after the DB was created. We use RunSQL with IF NOT EXISTS so this is safe
to run against a DB that may or may not already have the tables.

This migration does NOT change Django's model state (no CreateModel operations)
because 0001_initial already defines these models in the migration graph.
"""
from django.db import migrations


CREATE_SALES_AGENT_LOGS = """
CREATE TABLE IF NOT EXISTS sales_agent_logs (
    id TEXT PRIMARY KEY NOT NULL,
    stage VARCHAR(30) NOT NULL,
    confidence REAL NOT NULL,
    "decision" VARCHAR(30) NOT NULL,
    handoff_needed BOOLEAN NOT NULL,
    handoff_reason VARCHAR(200) NOT NULL,
    products_shown JSON NOT NULL,
    recommended_actions JSON NOT NULL,
    context_used JSON NOT NULL,
    created_at DATETIME NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
)
"""

CREATE_AI_AGENTS = """
CREATE TABLE IF NOT EXISTS ai_agents (
    id TEXT PRIMARY KEY NOT NULL,
    agent_type VARCHAR(20) NOT NULL,
    name VARCHAR(200) NOT NULL,
    is_active BOOLEAN NOT NULL,
    provider VARCHAR(20) NOT NULL,
    model VARCHAR(100) NOT NULL,
    system_prompt TEXT NOT NULL,
    tools JSON NOT NULL,
    config JSON NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (organization_id, agent_type)
)
"""

CREATE_IDX_SALES_LOG_ORG_STAGE = "CREATE INDEX IF NOT EXISTS sales_agent_organiz_118338_idx ON sales_agent_logs (organization_id, stage)"
CREATE_IDX_SALES_LOG_CONV = "CREATE INDEX IF NOT EXISTS sales_agent_convers_d1b4e1_idx ON sales_agent_logs (conversation_id)"


class Migration(migrations.Migration):

    dependencies = [
        ('ai_engine', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                CREATE_SALES_AGENT_LOGS,
                CREATE_AI_AGENTS,
                CREATE_IDX_SALES_LOG_ORG_STAGE,
                CREATE_IDX_SALES_LOG_CONV,
            ],
            reverse_sql=migrations.RunSQL.noop,
            # state_operations=[] means this does NOT alter Django's model state
        ),
    ]
