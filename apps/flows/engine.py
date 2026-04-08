"""
Flow Engine — runtime interpreter for DB-stored Flow definitions.

Executes flows defined in the Flow model (nodes + edges) as conversation
state machines. Any organization can build and run flows — no hardcoding required.

Node types
----------
start      Entry point. Auto-advances, no reply.
message    Sends static text. Auto-advances.
question   Sends text, waits for user reply, stores answer in a variable.
condition  Branches on a variable value or regex. Edges: 'yes' / 'no'.
action     Side effect: handoff, set_variable, webhook. Auto-advances.
ai_reply   Delegates this turn to the Sales Agent AI, then resumes flow.
end        Closes the flow. Optional closing message.

Edge schema
-----------
{
  "id": "...",
  "source": "<node_id>",
  "target": "<node_id>",
  "data": { "condition": "default" | "yes" | "no" | "option:<value>" }
}

Template variables available in text fields
-------------------------------------------
  {{contact_name}}   {{org_name}}   {{<any_variable>}}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FlowResult:
    """Return value from FlowEngine. Slots directly into SalesAgent.run()."""
    reply_text: str
    completed: bool = False
    variables: dict[str, Any] = field(default_factory=dict)
    handoff: bool = False
    handoff_reason: str = ''
    delegate_to_ai: bool = False
    flow_name: str = ''
    flow_id: str = ''
    current_node_id: str = ''


class FlowEngine:
    """Interprets DB-stored Flow definitions as conversation state machines."""

    # ── Public API ────────────────────────────────────────────────────────────

    def advance(self, *, conversation, message_text: str, sales_ctx) -> FlowResult | None:
        """
        If a DB flow is active in the conversation, advance it with this message.
        Returns None when no DB flow is active (lets the sales agent take over).
        """
        metadata = getattr(conversation, 'metadata', None) or {}
        active = metadata.get('active_flow') or {}

        if not active.get('flow_id'):
            return None
        if active.get('status') == 'completed':
            return None

        return self._advance_flow(
            conversation=conversation,
            active_flow=active,
            message_text=message_text,
            sales_ctx=sales_ctx,
        )

    def find_and_activate(
        self,
        *,
        conversation,
        message_text: str,
        channel: str,
        sales_ctx,
    ) -> FlowResult | None:
        """
        Check if any active DB Flow matches this message/channel and activate it.
        Returns a FlowResult for the first matching flow, or None.
        """
        from .trigger import find_matching_flow

        org = getattr(conversation, 'organization', None)
        if org is None:
            return None

        flow = find_matching_flow(
            organization=org,
            message_text=message_text,
            channel=channel,
        )
        if flow is None:
            return None

        return self._start_flow(
            conversation=conversation,
            flow=flow,
            message_text=message_text,
            sales_ctx=sales_ctx,
        )

    # ── Flow lifecycle ────────────────────────────────────────────────────────

    def _start_flow(self, *, conversation, flow, message_text: str, sales_ctx) -> FlowResult | None:
        from .serializers import split_flow_nodes

        visible_nodes, _, _ = split_flow_nodes(flow.nodes, flow.channel)
        nodes_by_id = {n['id']: n for n in visible_nodes if isinstance(n, dict) and n.get('id')}
        edges = flow.edges or []

        start_node = next(
            (n for n in visible_nodes if isinstance(n, dict) and n.get('tipo') == 'start'),
            visible_nodes[0] if visible_nodes else None,
        )
        if start_node is None:
            logger.warning('flow_engine_no_start_node', flow_id=str(flow.id))
            return None

        variables: dict[str, Any] = {}
        context = self._build_context(conversation, variables, sales_ctx, str(flow.id), flow.name)

        result, new_state = self._execute_from_node(
            node_id=start_node['id'],
            nodes_by_id=nodes_by_id,
            edges=edges,
            variables=variables,
            context=context,
            message_text=message_text,
        )

        active_flow_state = {
            'flow_id': str(flow.id),
            'name': flow.name,
            'current_node_id': new_state['current_node_id'],
            'step': new_state['current_node_id'],
            'status': new_state['status'],
            'variables': new_state['variables'],
            'data': new_state['variables'],
        }
        self._persist(conversation, active_flow_state)
        return result

    def _advance_flow(self, *, conversation, active_flow: dict, message_text: str, sales_ctx) -> FlowResult | None:
        from .models import Flow
        from .serializers import split_flow_nodes

        flow_id = active_flow.get('flow_id')
        try:
            flow = Flow.objects.get(id=flow_id, is_active=True)
        except Exception:
            logger.warning('flow_engine_flow_not_found', flow_id=flow_id)
            return None

        visible_nodes, _, _ = split_flow_nodes(flow.nodes, flow.channel)
        nodes_by_id = {n['id']: n for n in visible_nodes if isinstance(n, dict) and n.get('id')}
        edges = flow.edges or []

        current_node_id = active_flow.get('current_node_id') or active_flow.get('step')
        variables = {**(active_flow.get('variables') or active_flow.get('data') or {})}
        context = self._build_context(conversation, variables, sales_ctx, flow_id, flow.name)

        current_node = nodes_by_id.get(current_node_id)
        if current_node is None:
            logger.warning('flow_engine_node_not_found', node_id=current_node_id, flow_id=flow_id)
            return None

        result, new_state = self._process_and_advance(
            current_node=current_node,
            nodes_by_id=nodes_by_id,
            edges=edges,
            variables=variables,
            context=context,
            message_text=message_text,
        )

        active_flow.update({
            'current_node_id': new_state['current_node_id'],
            'step': new_state['current_node_id'],
            'status': new_state['status'],
            'variables': new_state['variables'],
            'data': new_state['variables'],
        })
        self._persist(conversation, active_flow)
        return result

    # ── Node execution ────────────────────────────────────────────────────────

    def _execute_from_node(
        self,
        *,
        node_id: str,
        nodes_by_id: dict,
        edges: list,
        variables: dict,
        context: dict,
        message_text: str,
    ) -> tuple[FlowResult, dict]:
        """
        Walk nodes starting from node_id, chaining through auto-advancing types
        (start, message, action, condition) until hitting a waiting node
        (question, ai_reply, end) or running out of edges.
        """
        replies: list[str] = []
        visited: set[str] = set()
        current_id: str | None = node_id

        while current_id and current_id not in visited:
            visited.add(current_id)
            node = nodes_by_id.get(current_id)
            if node is None:
                break

            tipo = node.get('tipo', '')
            data = self._node_data(node)

            if tipo == 'start':
                current_id = self._default_next(current_id, edges)
                continue

            if tipo == 'message':
                text = self._render(data['text'], context)
                if text:
                    replies.append(text)
                current_id = self._default_next(current_id, edges)
                continue

            if tipo in ('action', 'api'):
                action_result = self._execute_action_data(data, variables, context)
                if action_result.get('handoff'):
                    return FlowResult(
                        reply_text=self._join(replies),
                        handoff=True,
                        handoff_reason=action_result.get('reason', ''),
                        variables=variables,
                        current_node_id=current_id,
                        flow_name=context['flow_name'],
                        flow_id=context['flow_id'],
                    ), {'current_node_id': current_id, 'status': 'completed', 'variables': variables}
                current_id = self._default_next(current_id, edges)
                continue

            if tipo == 'condition':
                condition_met = self._evaluate_condition_data(data, variables, message_text)
                next_id = self._conditional_next(current_id, 'yes' if condition_met else 'no', edges)
                current_id = next_id or self._default_next(current_id, edges)
                continue

            if tipo in ('question', 'collect'):
                text = self._render(data['text'], context)
                if text:
                    replies.append(text)
                return FlowResult(
                    reply_text=self._join(replies),
                    variables=variables,
                    current_node_id=current_id,
                    flow_name=context['flow_name'],
                    flow_id=context['flow_id'],
                ), {'current_node_id': current_id, 'status': 'active', 'variables': variables}

            if tipo == 'quickReply':
                text = self._render(data['text'], context)
                options = [str(o) for o in (data.get('options') or [])]
                if text:
                    replies.append(text)
                if options:
                    replies.append('\n'.join(f'· {o}' for o in options))
                return FlowResult(
                    reply_text=self._join(replies),
                    variables=variables,
                    current_node_id=current_id,
                    flow_name=context['flow_name'],
                    flow_id=context['flow_id'],
                ), {'current_node_id': current_id, 'status': 'active', 'variables': variables}

            if tipo == 'ai_reply':
                return FlowResult(
                    reply_text=self._join(replies),
                    delegate_to_ai=True,
                    variables=variables,
                    current_node_id=current_id,
                    flow_name=context['flow_name'],
                    flow_id=context['flow_id'],
                ), {'current_node_id': current_id, 'status': 'active', 'variables': variables}

            if tipo == 'media':
                text = self._render(data.get('text') or '', context)
                if text:
                    replies.append(text)
                media_url = data.get('mediaUrl') or ''
                if media_url:
                    replies.append(media_url)
                current_id = self._default_next(current_id, edges)
                continue

            if tipo == 'delay':
                # No actual delay in synchronous execution — just advance
                current_id = self._default_next(current_id, edges)
                continue

            if tipo == 'tag':
                tag_value = str(data.get('tagValue') or '')
                if tag_value:
                    self._apply_tag(context.get('conversation'), tag_value)
                current_id = self._default_next(current_id, edges)
                continue

            if tipo == 'escalate':
                msg = self._render(data.get('text') or '', context)
                if msg:
                    replies.append(msg)
                return FlowResult(
                    reply_text=self._join(replies),
                    handoff=True,
                    handoff_reason=str(data.get('reason') or 'flow_escalation'),
                    variables=variables,
                    current_node_id=current_id,
                    flow_name=context['flow_name'],
                    flow_id=context['flow_id'],
                ), {'current_node_id': current_id, 'status': 'completed', 'variables': variables}

            if tipo == 'end':
                closing = self._render(data.get('message') or data.get('text') or '', context)
                if closing:
                    replies.append(closing)
                return FlowResult(
                    reply_text=self._join(replies),
                    completed=True,
                    variables=variables,
                    current_node_id=current_id,
                    flow_name=context['flow_name'],
                    flow_id=context['flow_id'],
                ), {'current_node_id': current_id, 'status': 'completed', 'variables': variables}

            # Unknown type — skip forward
            current_id = self._default_next(current_id, edges)

        # Ran out of nodes
        return FlowResult(
            reply_text=self._join(replies),
            completed=True,
            variables=variables,
            current_node_id=current_id or node_id,
            flow_name=context['flow_name'],
            flow_id=context['flow_id'],
        ), {'current_node_id': current_id or node_id, 'status': 'completed', 'variables': variables}

    def _process_and_advance(
        self,
        *,
        current_node: dict,
        nodes_by_id: dict,
        edges: list,
        variables: dict,
        context: dict,
        message_text: str,
    ) -> tuple[FlowResult, dict]:
        """Apply user's answer to current_node, store variable, then advance."""
        tipo = current_node.get('tipo', '')
        data = self._node_data(current_node)
        current_id = current_node['id']

        if tipo in ('question', 'collect'):
            variable = data.get('variable')
            input_type = data.get('input_type', 'text')
            options = [str(o) for o in (data.get('options') or [])]

            parsed = self._parse_input(message_text, input_type, options)
            if parsed is None:
                # Invalid — repeat question with hint
                hint = self._input_hint(input_type, options)
                question_text = self._render(data.get('text', ''), context)
                reply = f'{hint}\n{question_text}' if hint else question_text
                return FlowResult(
                    reply_text=reply,
                    variables=variables,
                    current_node_id=current_id,
                    flow_name=context['flow_name'],
                    flow_id=context['flow_id'],
                ), {'current_node_id': current_id, 'status': 'active', 'variables': variables}

            if variable:
                variables[variable] = parsed
                context['variables'] = variables

            # Branch on selected option, or default edge
            if options and isinstance(parsed, str):
                next_id = (
                    self._conditional_next(current_id, f'option:{parsed}', edges)
                    or self._default_next(current_id, edges)
                )
            else:
                next_id = self._default_next(current_id, edges)

        elif tipo == 'quickReply':
            variable = data.get('variable')
            options = [str(o) for o in (data.get('options') or [])]
            parsed: Any = None
            if options:
                parsed = self._parse_input(message_text, 'option', options)
            if parsed is None:
                parsed = (message_text or '').strip() or None
            if variable and parsed:
                variables[variable] = parsed
                context['variables'] = variables
            if options and isinstance(parsed, str):
                next_id = (
                    self._conditional_next(current_id, f'option:{parsed}', edges)
                    or self._default_next(current_id, edges)
                )
            else:
                next_id = self._default_next(current_id, edges)

        elif tipo == 'condition':
            met = self._evaluate_condition_data(data, variables, message_text)
            next_id = (
                self._conditional_next(current_id, 'yes' if met else 'no', edges)
                or self._default_next(current_id, edges)
            )

        elif tipo == 'ai_reply':
            # After AI reply, advance to next node
            next_id = self._default_next(current_id, edges)

        else:
            next_id = self._default_next(current_id, edges)

        if next_id is None:
            return FlowResult(
                reply_text='',
                completed=True,
                variables=variables,
                current_node_id=current_id,
                flow_name=context['flow_name'],
                flow_id=context['flow_id'],
            ), {'current_node_id': current_id, 'status': 'completed', 'variables': variables}

        return self._execute_from_node(
            node_id=next_id,
            nodes_by_id=nodes_by_id,
            edges=edges,
            variables=variables,
            context=context,
            message_text=message_text,
        )

    # ── Action execution ──────────────────────────────────────────────────────

    def _execute_action_data(self, data: dict, variables: dict, context: dict) -> dict:
        """Execute action from already-extracted data dict."""
        action_type = data.get('action_type', '')
        payload = data.get('payload') or {}

        if action_type == 'handoff':
            return {'handoff': True, 'reason': payload.get('reason', 'flow_handoff')}

        if action_type == 'set_variable':
            key = payload.get('variable')
            val = payload.get('value')
            if key:
                variables[key] = val
                context['variables'] = variables

        if action_type == 'webhook':
            self._fire_webhook(payload, variables)

        return {}

    def _execute_action(self, node: dict, variables: dict, context: dict) -> dict:
        data = node.get('data') or {}
        action_type = data.get('action_type', '')
        payload = data.get('payload') or {}

        if action_type == 'handoff':
            return {'handoff': True, 'reason': payload.get('reason', 'flow_handoff')}

        if action_type == 'set_variable':
            key = payload.get('variable')
            val = payload.get('value')
            if key:
                variables[key] = val
                context['variables'] = variables

        if action_type == 'webhook':
            self._fire_webhook(payload, variables)

        return {}

    def _fire_webhook(self, payload: dict, variables: dict) -> None:
        import json
        import threading
        import urllib.request

        url = payload.get('url', '')
        if not url:
            return

        body = json.dumps({**payload.get('body', {}), 'variables': variables}).encode()

        def _send() -> None:
            try:
                req = urllib.request.Request(
                    url, data=body,
                    headers={'Content-Type': 'application/json'},
                    method='POST',
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass

        threading.Thread(target=_send, daemon=True).start()

    # ── Condition evaluation ──────────────────────────────────────────────────

    def _evaluate_condition_data(self, data: dict, variables: dict, message_text: str) -> bool:
        """Evaluate condition from already-extracted data dict."""
        variable = data.get('variable', '')
        operator = data.get('operator', 'eq')
        value = str(data.get('value', ''))

        current = str(variables.get(variable, message_text or '')).lower().strip()
        value_lower = value.lower().strip()

        ops: dict[str, Any] = {
            'eq': lambda a, b: a == b,
            'neq': lambda a, b: a != b,
            'contains': lambda a, b: b in a,
            'not_contains': lambda a, b: b not in a,
            'starts_with': lambda a, b: a.startswith(b),
            'in': lambda a, b: a in [x.strip() for x in b.split(',')],
        }
        if operator in ops:
            return ops[operator](current, value_lower)

        numeric_ops = {'gt': '>', 'lt': '<', 'gte': '>=', 'lte': '<='}
        if operator in numeric_ops:
            try:
                return eval(f'{float(current)} {numeric_ops[operator]} {float(value_lower)}')  # noqa: S307
            except (ValueError, TypeError):
                return False

        if operator == 'regex':
            try:
                return bool(re.search(value, current))
            except re.error:
                return False

        return False

    def _evaluate_condition(self, node: dict, variables: dict, message_text: str) -> bool:
        data = node.get('data') or {}
        variable = data.get('variable', '')
        operator = data.get('operator', 'eq')
        value = str(data.get('value', ''))

        current = str(variables.get(variable, message_text or '')).lower().strip()
        value_lower = value.lower().strip()

        ops: dict[str, Any] = {
            'eq': lambda a, b: a == b,
            'neq': lambda a, b: a != b,
            'contains': lambda a, b: b in a,
            'not_contains': lambda a, b: b not in a,
            'starts_with': lambda a, b: a.startswith(b),
            'in': lambda a, b: a in [x.strip() for x in b.split(',')],
        }
        if operator in ops:
            return ops[operator](current, value_lower)

        numeric_ops = {'gt': '>', 'lt': '<', 'gte': '>=', 'lte': '<='}
        if operator in numeric_ops:
            try:
                return eval(f'{float(current)} {numeric_ops[operator]} {float(value_lower)}')  # noqa: S307
            except (ValueError, TypeError):
                return False

        if operator == 'regex':
            try:
                return bool(re.search(value, current))
            except re.error:
                return False

        return False

    # ── Input parsing ─────────────────────────────────────────────────────────

    def _parse_input(self, message_text: str, input_type: str, options: list[str]) -> Any:
        text = (message_text or '').strip()

        if input_type == 'number':
            m = re.search(r'\d+(?:[.,]\d+)?', text)
            return float(m.group().replace(',', '.')) if m else None

        if input_type == 'email':
            m = re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', text.lower())
            return m.group() if m else None

        if input_type == 'phone':
            m = re.search(r'[\d\s+\-()]{7,}', text)
            return m.group().strip() if m else None

        if input_type == 'option' and options:
            normalized = text.lower().strip()
            for opt in options:
                if normalized == opt.lower():
                    return opt
            for opt in options:
                if opt.lower() in normalized or normalized in opt.lower():
                    return opt
            return None

        return text or None

    def _input_hint(self, input_type: str, options: list[str]) -> str:
        if input_type == 'number':
            return 'Por favor escribe un número.'
        if input_type == 'email':
            return 'Por favor escribe un correo electrónico válido.'
        if input_type == 'phone':
            return 'Por favor escribe un número de teléfono.'
        if input_type == 'option' and options:
            return f'Por favor elige una opción: {", ".join(options)}.'
        return ''

    # ── Edge navigation ───────────────────────────────────────────────────────

    def _default_next(self, node_id: str, edges: list) -> str | None:
        default = None
        first = None
        for edge in edges:
            if not isinstance(edge, dict) or edge.get('source') != node_id:
                continue
            cond = (edge.get('data') or {}).get('condition', 'default')
            if first is None:
                first = edge.get('target')
            if cond in ('default', '', None):
                default = edge.get('target')
                break
        return default or first

    def _conditional_next(self, node_id: str, condition_label: str, edges: list) -> str | None:
        for edge in edges:
            if not isinstance(edge, dict) or edge.get('source') != node_id:
                continue
            if (edge.get('data') or {}).get('condition') == condition_label:
                return edge.get('target')
        return None

    # ── Template rendering ────────────────────────────────────────────────────

    def _render(self, template: str, context: dict) -> str:
        if not template:
            return ''
        result = template
        result = result.replace('{{contact_name}}', str(context.get('contact_name', 'tú')))
        result = result.replace('{{org_name}}', str(context.get('org_name', '')))
        for key, value in (context.get('variables') or {}).items():
            result = result.replace(f'{{{{{key}}}}}', str(value))
        return result

    def _join(self, parts: list[str]) -> str:
        return '\n'.join(p for p in parts if p).strip()

    # ── Context builder ───────────────────────────────────────────────────────

    def _build_context(
        self, conversation, variables: dict, sales_ctx, flow_id: str, flow_name: str
    ) -> dict:
        contact = getattr(conversation, 'contact', None)
        contact_name = ''
        if contact:
            contact_name = (
                getattr(contact, 'name', '')
                or getattr(contact, 'phone', '')
                or ''
            )
        org_name = ''
        if sales_ctx:
            org_name = (
                getattr(sales_ctx.business, 'org_name', '')
                or getattr(sales_ctx.brand, 'brand_name', '')
                or ''
            )
        return {
            'contact_name': contact_name,
            'org_name': org_name,
            'variables': variables,
            'flow_id': flow_id,
            'flow_name': flow_name,
            'conversation': conversation,
        }

    # ── Node data extraction (supports both nested and legacy flat formats) ────

    def _node_data(self, node: dict) -> dict:
        """Extract node data supporting both {data:{...}} and legacy flat formats."""
        nested = node.get('data') or {}
        def first(*vals):
            for v in vals:
                if v is not None and v != '':
                    return v
            return None

        return {
            'text': first(nested.get('text'), node.get('contenido'), node.get('pregunta'), ''),
            'options': first(nested.get('options'), node.get('opciones'), []),
            'variable': first(nested.get('variable'), node.get('variable'), ''),
            'input_type': first(nested.get('input_type'), node.get('input_type'), 'text'),
            'operator': first(nested.get('operator'), node.get('operator'), 'eq'),
            'value': first(nested.get('value'), node.get('value'), ''),
            'action_type': first(nested.get('action_type'), node.get('action_type'), ''),
            'payload': first(nested.get('payload'), node.get('payload'), {}),
            'mediaType': first(nested.get('mediaType'), node.get('mediaType'), ''),
            'mediaUrl': first(nested.get('mediaUrl'), node.get('mediaUrl'), ''),
            'delayMs': first(nested.get('delayMs'), node.get('delayMs'), 0),
            'tagValue': first(nested.get('tagValue'), node.get('tagValue'), ''),
            'message': first(nested.get('message'), nested.get('text'), node.get('message'), ''),
            'reason': first(nested.get('reason'), node.get('reason'), 'flow_handoff'),
        }

    # ── Tag helper ────────────────────────────────────────────────────────────

    def _apply_tag(self, conversation, tag_value: str) -> None:
        if not tag_value or not conversation:
            return
        try:
            metadata = {**(getattr(conversation, 'metadata', None) or {})}
            tags = list(metadata.get('tags') or [])
            if tag_value not in tags:
                tags.append(tag_value)
            metadata['tags'] = tags
            conversation.metadata = metadata
            conversation.save(update_fields=['metadata', 'updated_at'])
        except Exception:
            pass

    # ── Persistence ───────────────────────────────────────────────────────────

    def _persist(self, conversation, active_flow_state: dict) -> None:
        metadata = {**(getattr(conversation, 'metadata', None) or {})}
        if active_flow_state.get('status') == 'completed':
            metadata.pop('active_flow', None)
        else:
            metadata['active_flow'] = active_flow_state
        conversation.metadata = metadata
        conversation.save(update_fields=['metadata', 'updated_at'])
