from django.db import migrations

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS openai_usage_logs (
    id TEXT PRIMARY KEY NOT NULL,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    feature VARCHAR(40) NOT NULL DEFAULT 'other',
    model_name VARCHAR(100) NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd DECIMAL(10,6) NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL
)
"""

CREATE_IDX_ORG = "CREATE INDEX IF NOT EXISTS openai_usage_org_created_idx ON openai_usage_logs (organization_id, created_at DESC)"
CREATE_IDX_FEATURE = "CREATE INDEX IF NOT EXISTS openai_usage_feature_idx ON openai_usage_logs (organization_id, feature, created_at DESC)"


class Migration(migrations.Migration):

    dependencies = [
        ('ai_engine', '0002_create_missing_tables'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[CREATE_TABLE, CREATE_IDX_ORG, CREATE_IDX_FEATURE],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
