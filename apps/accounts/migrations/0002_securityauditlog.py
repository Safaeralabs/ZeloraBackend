import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SecurityAuditLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('actor_email', models.EmailField(blank=True)),
                ('event_type', models.CharField(choices=[
                    ('login_success', 'Login exitoso'),
                    ('login_failed', 'Login fallido'),
                    ('login_blocked_ip', 'Login bloqueado por IP'),
                    ('password_changed', 'Contrasena cambiada'),
                    ('security_settings_changed', 'Configuracion de seguridad cambiada'),
                    ('agent_created', 'Agente creado'),
                    ('agent_deleted', 'Agente eliminado'),
                    ('ip_allowlist_changed', 'Lista blanca IP cambiada'),
                ], max_length=50)),
                ('event_description', models.CharField(max_length=500)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=300)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='audit_logs',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='audit_logs',
                    to='accounts.organization',
                )),
            ],
            options={
                'db_table': 'security_audit_logs',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['organization', '-created_at'], name='sec_audit_org_date_idx'),
                    models.Index(fields=['organization', 'event_type'], name='sec_audit_org_type_idx'),
                ],
            },
        ),
    ]
