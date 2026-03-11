from rest_framework import serializers
from .models import ChannelConfig


class ChannelConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChannelConfig
        exclude = ['credentials']  # Never expose credentials
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']
