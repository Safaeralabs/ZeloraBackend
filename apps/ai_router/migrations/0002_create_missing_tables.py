"""
Create router_decision_logs table using RunSQL.

This table was missing from the original syncdb because the model was added
after the DB was created. RunSQL with IF NOT EXISTS is safe to run on any DB.

This migration does NOT change Django's model state (no CreateModel) because
0001_initial already defines RouterDecisionLog in the migration graph.
"""
from django.db import migrations


CREATE_ROUTER_DECISION_LOGS = """
CREATE TABLE IF NOT EXISTS router_decision_logs (
    id TEXT PRIMARY KEY NOT NULL,
    decision_id VARCHAR(100) NOT NULL,
    intent VARCHAR(100) NOT NULL,
    confidence REAL NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    route_type VARCHAR(60) NOT NULL,
    agent VARCHAR(100) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    post_actions JSON NOT NULL,
    full_decision JSON NOT NULL,
    created_at DATETIME NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
)
"""

CREATE_IDX_ORG_CREATED = "CREATE INDEX IF NOT EXISTS router_deci_organiz_7cd640_idx ON router_decision_logs (organization_id, created_at DESC)"
CREATE_IDX_CONV = "CREATE INDEX IF NOT EXISTS router_deci_convers_a23a48_idx ON router_decision_logs (conversation_id)"
CREATE_IDX_INTENT = "CREATE INDEX IF NOT EXISTS router_deci_intent_aaabe6_idx ON router_decision_logs (intent)"


class Migration(migrations.Migration):

    dependencies = [
        ('ai_router', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                CREATE_ROUTER_DECISION_LOGS,
                CREATE_IDX_ORG_CREATED,
                CREATE_IDX_CONV,
                CREATE_IDX_INTENT,
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
