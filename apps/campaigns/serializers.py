from rest_framework import serializers
from .models import Template, Campaign


class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']


class CampaignSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.name', read_only=True)

    class Meta:
        model = Campaign
        fields = '__all__'
        read_only_fields = [
            'id', 'organization', 'sent_at', 'delivered', 'read', 'failed', 'created_at'
        ]
