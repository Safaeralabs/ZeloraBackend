# Sales Agent Logging Guide

El sales agent ahora loguea **todo** lo que hace. Esta guía te ayuda a entender qué esperar.

---

## 📊 Flujo Completo de Logs

### 1. **Entrada al Agent**
```
sales_agent_run_start
├─ conversation_id: UUID
├─ organization_id: UUID  
├─ message_text: "quiero un regalo para mi novia"
└─ router_decision: {...}
```

### 2. **Carga de Contexto**
```
sales_context_loaded (debug)
├─ org_name: "Mi Empresa"
└─ agent_name: "Sales Agent"

contact_memory_loaded (debug)
├─ has_prior_interactions: true/false
├─ conversation_count: 3
└─ converted: true/false
```

### 3. **DB-Driven Flows** (si aplica)
```
db_flow_engine_start (debug)
├─ channel: "web"

db_flow_handled_request (info) — Si un flow maneró la solicitud
├─ flow_id: "flow_123"
├─ flow_name: "Checkout Flow"
├─ stage: "closed_won"
└─ completed: true

[RETURN AQUÍ SI HUBIERA FLOW — el resto de logs no se genera]
```

### 4. **Clasificación de Comprador**
```
classifying_stage_and_buyer (debug)

stage_classified (debug)
├─ stage: "considering"
└─ confidence: 0.88

stage_matched_via_heuristic (debug) — Cómo se detectó el stage
├─ stage: "considering"
└─ confidence: 0.88

buyer_profiled (debug) — Perfil completo del comprador
├─ priority: "price"
├─ urgency: "immediate"
├─ objection: null
├─ style: "direct"
├─ archetype: "gift_buyer"  ⭐ P.5
├─ quantity: "single"
├─ budget_max: 50000.0  ⭐ P.1
└─ budget_min: null
```

### 5. **Detección de Señales**
```
close_signals_detected (debug)
└─ signals: ["explicit_buy_intent", "payment_intent"]

handoff_checked (debug)
├─ needed: false
└─ reason: null

[O si escala:]
escalating_to_human (info)
├─ handoff_reason: "negotiation_request:precio especial"
└─ stage: "considering"

[Ejemplos de razones de escalate:]
escalating_for_negotiation (info)
escalating_bulk_order (info)
escalating_high_volume_order (info)
├─ qty: 50
└─ auto_limit: 10
```

### 6. **Búsqueda de Productos**
```
looking_up_products (debug)
└─ query: "ropa para regalo"

products_found (debug)
└─ count: 12

scoring_products (debug)
├─ total: 12
└─ prior_shown: 3

products_ranked (debug)
└─ top_3: ["prod_123", "prod_456", "prod_789"]
```

### 7. **Stock y Promotions**
```
promotions_loaded (debug)
└─ count: 2

checking_stock (debug)
└─ product_id: "prod_123"

stock_checked (debug)
└─ in_stock: true

order_history_loaded (debug)
└─ count: 5
```

### 8. **Generación de Reply**
```
generate_reply_start (debug)
├─ stage: "considering"
├─ channel: "web"
├─ products_count: 3
└─ buyer_archetype: "gift_buyer"

[Si usa heurística fallback:]
heuristic_reply_triggered (debug)
├─ stage: "considering"
└─ objection: null

[Si llama al LLM:]
calling_llm_reply (debug)

retrieving_few_shot_examples (debug)
└─ stage: "considering"

few_shot_examples_found (debug)
└─ count: 2

llm_reply_chat_history (debug)
├─ message_count: 4
└─ is_first_message: false

calling_openai_api (info) ⭐ LLAMADA A OPENAI
├─ model: "gpt-4o"
├─ temperature: 0.6
├─ max_tokens: 180
├─ message_count: 5
├─ system_prompt_length: 4500
└─ context_block_length: 2300

openai_api_response (info) ⭐ RESPUESTA DE OPENAI
├─ model: "gpt-4o"
├─ latency_ms: 450
├─ prompt_tokens: 1200
├─ completion_tokens: 45
├─ total_tokens: 1245
└─ response_preview: "Entiendo que buscas un regalo perfecto..."
```

### 9. **Post-Procesamiento**
```
applying_brand_voice (debug)
├─ stage: "considering"
├─ tone: "cercano"
└─ formality: "balanced"

enforcing_reply_scope (debug)
└─ stage: "considering"

strengthening_closing_reply (debug)
├─ stage: "considering"
└─ signals: ["availability_check"]
```

### 10. **Actions y Follow-up**
```
actions_built (debug)
├─ count: 3
└─ actions: ["answer_question", "suggest_product", "close_sale"]

creating_followup_task (debug)
├─ stage: "follow_up_needed"
└─ mode: "suave"

updating_contact_memory (debug)
└─ contact_id: "contact_456"
```

### 11. **Resultado Final**
```
sales_agent_run_complete (info) ✅ FIN DEL FLUJO
├─ stage: "considering"
├─ decision: "recommend"
├─ confidence: 0.88
├─ products_shown: 2
└─ actions_count: 3
```

---

## 🔍 Dónde Buscar Logs

**Archivo de logs principal:**
```
backendv2/logs/vendly.json.log
```

**Ver logs en tiempo real:**
```bash
tail -f backendv2/logs/vendly.json.log | jq .
```

**Filtrar por conversación:**
```bash
cat backendv2/logs/vendly.json.log | jq 'select(.conversation_id=="UUID-AQUI")'
```

**Filtrar por nivel:**
```bash
cat backendv2/logs/vendly.json.log | jq 'select(.level=="WARNING" or .level=="ERROR")'
```

---

## 📈 Logs Principales Por Propósito

### Para debuggear por qué escala a humano
```
escalating_to_human
escalating_for_negotiation
escalating_bulk_order
escalating_high_volume_order
```

### Para auditar llamadas a OpenAI
```
calling_openai_api (qué se envió)
openai_api_response (qué respondió)
```

### Para entender buyer profiling
```
buyer_profiled (priority, archetype, budget)
stage_matched_via_heuristic (por qué stage)
close_signals_detected (qué señales de cierre)
```

### Para ver product recommendation
```
products_ranked (qué se mostró)
stock_checked (si hay stock)
```

### Para validar feature flags
```
few_shot_examples_found / no_few_shot_examples_found
negotiation_handled_by_llm
db_flow_handled_request
```

---

## 📝 Niveles de Log

- **INFO**: Decisiones importantes (escalate, LLM call, result)
- **DEBUG**: Detalles de extracción (buyer, stage, products, signals)
- **WARNING**: Excepciones esperadas (db_flow_error, usage_tracking_error)
- **ERROR**: Errores que impiden el flujo

---

## 🎯 Ejemplos de Búsqueda

**"¿Por qué el agente no recomendó ningún producto?"**
```bash
cat backendv2/logs/vendly.json.log | jq 'select(.conversation_id=="X" and .event=="products_ranked")'
# Si count=0, el lookup no encontró nada
```

**"¿Cuánto tardó la llamada a OpenAI?"**
```bash
cat backendv2/logs/vendly.json.log | jq 'select(.event=="openai_api_response") | .latency_ms'
```

**"¿Se detectó la ocasión de regalo?"**
```bash
cat backendv2/logs/vendly.json.log | jq 'select(.event=="buyer_profiled") | {archetype, stage}'
```

**"¿Por qué se escaló?"**
```bash
cat backendv2/logs/vendly.json.log | jq 'select(.event | test("escalating"))'
```

---

## 💡 Tips

1. **Los logs están en JSON** → Piping con `jq` es tu amigo
2. **Busca `sales_agent_run_start` y `sales_agent_run_complete`** → Enmarcan un turno completo
3. **Busca `openai_api_response`** → Para auditar costos y latencias
4. **Los timestamps están en ISO 8601** → Fácil de filterizar por rango horario
5. **`conversation_id` es tu amiga** → Filtra por ella para ver un diálogo completo

---

Generated: 2026-04-13
