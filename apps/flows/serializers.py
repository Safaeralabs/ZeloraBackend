from rest_framework import serializers
from .models import Flow


class FlowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flow
        fields = '__all__'
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']
