from rest_framework import serializers
from .models import Flow

FLOW_META_ID = '__flow_meta__'
DEFAULT_ROUTER_CONFIG = {
    'triggerType': 'intent',
    'intent': 'unknown',
    'keywords': [],
    'confidenceThreshold': 0.8,
    'fallbackAction': 'request_clarification',
}


def split_flow_nodes(nodes, fallback_channel='whatsapp'):
    nodes = nodes or []
    meta = next(
        (
            node
            for node in nodes
            if isinstance(node, dict) and (node.get('id') == FLOW_META_ID or node.get('tipo') == '__meta__')
        ),
        {},
    )
    visible_nodes = [
        node
        for node in nodes
        if not (isinstance(node, dict) and (node.get('id') == FLOW_META_ID or node.get('tipo') == '__meta__'))
    ]
    canales = meta.get('canales') or ([fallback_channel] if fallback_channel else ['whatsapp'])
    router_config = {**DEFAULT_ROUTER_CONFIG, **(meta.get('router_config') or {})}
    return visible_nodes, router_config, canales


def pack_flow_nodes(nodes, router_config, canales):
    visible_nodes, _, _ = split_flow_nodes(nodes)
    meta_node = {
        'id': FLOW_META_ID,
        'tipo': '__meta__',
        'router_config': {**DEFAULT_ROUTER_CONFIG, **(router_config or {})},
        'canales': canales or ['whatsapp'],
    }
    return [*visible_nodes, meta_node]


class FlowSerializer(serializers.ModelSerializer):
    router_config = serializers.JSONField(required=False)
    canales = serializers.ListField(child=serializers.CharField(), required=False)

    class Meta:
        model = Flow
        fields = [
            'id',
            'organization',
            'name',
            'description',
            'nodes',
            'edges',
            'trigger',
            'channel',
            'is_active',
            'router_config',
            'canales',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        visible_nodes, router_config, canales = split_flow_nodes(instance.nodes, instance.channel)
        data['nodes'] = visible_nodes
        data['router_config'] = router_config
        data['canales'] = canales
        return data

    def create(self, validated_data):
        router_config = validated_data.pop('router_config', DEFAULT_ROUTER_CONFIG)
        canales = validated_data.pop('canales', None) or [validated_data.get('channel') or 'whatsapp']
        validated_data['channel'] = canales[0]
        validated_data['trigger'] = router_config.get('intent', validated_data.get('trigger', 'unknown'))
        validated_data['nodes'] = pack_flow_nodes(validated_data.get('nodes', []), router_config, canales)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        router_config = validated_data.pop('router_config', None)
        canales = validated_data.pop('canales', None)

        current_nodes, current_router_config, current_canales = split_flow_nodes(instance.nodes, instance.channel)
        next_nodes = validated_data.get('nodes', current_nodes)
        next_router_config = {**current_router_config, **(router_config or {})}
        next_canales = canales or current_canales

        validated_data['channel'] = next_canales[0] if next_canales else instance.channel
        validated_data['trigger'] = next_router_config.get('intent', instance.trigger)
        validated_data['nodes'] = pack_flow_nodes(next_nodes, next_router_config, next_canales)
        return super().update(instance, validated_data)
