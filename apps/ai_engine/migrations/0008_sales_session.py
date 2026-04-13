# Generated migration for SalesSession model

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('ai_engine', '0007_remove_sales_agent'),
        ('conversations', '0001_initial'),  # Ensure Conversation model exists
        ('accounts', '0001_initial'),  # Ensure Organization model exists
    ]

    operations = [
        migrations.CreateModel(
            name='SalesSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('stage', models.CharField(
                    choices=[
                        ('discovery', 'Discovery'),
                        ('considering', 'Considering'),
                        ('checkout', 'Checkout'),
                        ('handoff', 'Handoff to Human'),
                        ('closed', 'Closed')
                    ],
                    default='discovery',
                    help_text='Current position in the sales funnel',
                    max_length=20
                )),
                ('situation', models.CharField(
                    choices=[
                        ('discovery', 'Discovery'),
                        ('confused_customer', 'Confused Customer'),
                        ('indecisive_customer', 'Indecisive Customer'),
                        ('comparing_customer', 'Comparing Customer'),
                        ('price_sensitive_customer', 'Price Sensitive Customer'),
                        ('specific_product_customer', 'Specific Product Customer'),
                        ('ready_to_buy_customer', 'Ready to Buy Customer'),
                        ('urgent_customer', 'Urgent Customer'),
                        ('expansion_opportunity', 'Expansion Opportunity'),
                        ('gift_customer', 'Gift Customer'),
                        ('objection_customer', 'Objection Customer'),
                        ('post_sale', 'Post Sale'),
                        ('logistics_customer', 'Logistics Customer'),
                        ('administrative_customer', 'Administrative Customer'),
                        ('changing_mind_customer', 'Changing Mind Customer'),
                        ('inactive_customer', 'Inactive Customer'),
                        ('out_of_catalog', 'Out of Catalog'),
                        ('off_topic', 'Off Topic'),
                        ('prompt_injection', 'Prompt Injection'),
                        ('checkout', 'Checkout')
                    ],
                    default='discovery',
                    help_text='Detected customer situation/context',
                    max_length=30
                )),
                ('intent', models.CharField(
                    blank=True,
                    default='',
                    help_text='Detected intent (buy_intent, price_inquiry, etc.)',
                    max_length=100
                )),
                ('budget_min', models.DecimalField(
                    blank=True,
                    decimal_places=2,
                    help_text='Inferred minimum budget',
                    max_digits=12,
                    null=True
                )),
                ('budget_max', models.DecimalField(
                    blank=True,
                    decimal_places=2,
                    help_text='Inferred maximum budget',
                    max_digits=12,
                    null=True
                )),
                ('category_interest', models.CharField(
                    blank=True,
                    default='',
                    help_text='Product category customer is interested in',
                    max_length=100
                )),
                ('selected_products', models.JSONField(
                    blank=True,
                    default=list,
                    help_text='List of product UUIDs customer has selected/liked'
                )),
                ('shown_products', models.JSONField(
                    blank=True,
                    default=list,
                    help_text='List of product UUIDs already shown (avoid repetition)'
                )),
                ('objections', models.JSONField(
                    blank=True,
                    default=list,
                    help_text='List of detected objections (price, shipping, quality, etc.)'
                )),
                ('shipping_city', models.CharField(
                    blank=True,
                    default='',
                    help_text='Detected or stated shipping location',
                    max_length=100
                )),
                ('checkout_step', models.PositiveSmallIntegerField(
                    default=0,
                    help_text='0=none, 1=confirm_products, 2=confirm_total, 3=payment_method, etc.'
                )),
                ('checkout_data', models.JSONField(
                    blank=True,
                    default=dict,
                    help_text='Temporary cart, total, payment method selection, etc.'
                )),
                ('message_count', models.PositiveIntegerField(default=0)),
                ('last_situation', models.CharField(
                    blank=True,
                    default='',
                    help_text='Previous situation detected (for change detection)',
                    max_length=30
                )),
                ('summary', models.TextField(
                    blank=True,
                    default='',
                    help_text='LLM-generated summary when context exceeds threshold'
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('conversation', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sales_session',
                    to='conversations.conversation'
                )),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sales_sessions',
                    to='accounts.organization'
                )),
            ],
            options={
                'db_table': 'sales_sessions',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='salessession',
            index=models.Index(fields=['organization', 'stage'], name='sales_sessi_organiz_idx'),
        ),
        migrations.AddIndex(
            model_name='salessession',
            index=models.Index(fields=['organization', 'updated_at'], name='sales_sessi_organiz_2_idx'),
        ),
        migrations.AddIndex(
            model_name='salessession',
            index=models.Index(fields=['conversation'], name='sales_sessi_conversa_idx'),
        ),
    ]
