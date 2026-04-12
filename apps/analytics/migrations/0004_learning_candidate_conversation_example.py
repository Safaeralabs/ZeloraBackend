# L3+L4: Add conversation_example kind to LearningCandidate

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0003_metrics_snapshot_commercial_metrics'),
    ]

    operations = [
        # No schema change needed — KIND_CHOICES is just text in the field definition.
        # The new 'conversation_example' choice can be used immediately.
        # This migration is a placeholder to mark the feature boundary.
    ]
