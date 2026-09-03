# WeCom Admin Rule Status And Global Message Format Design

## Goal

Extend the current admin backend in two focused ways:

- allow operators to disable, restore, and permanently delete individual rules
- add a global message format management page that controls which message fields are shown, what their labels display as, and which preset template is active

This iteration is intended to support day-to-day operations without introducing arbitrary free-form template editing.

## Scope

This design covers:

- rule status controls in the existing rule management page
- persistence for active and disabled rule status
- permanent deletion flow for rules
- a new global format management page
- database-backed storage for one active global message format configuration
- message builder integration with that global format configuration and preset templates
- admin tests for status switching and format-driven message output

This design does not cover:

- per-rule message format overrides
- arbitrary markdown template editing
- replacing the current CSV or local image compatibility path

## Current Context

The current backend already has:

- multi-rule persistence with `RuleGroup` and `RuleCondition`
- a rules list page and rule creation page
- a server-rendered admin UI
- a working message builder that currently hardcodes the output fields

The current gaps are operational:

- rules cannot be disabled, permanently deleted, or restored from the UI
- message content is fixed in code
- operators cannot hide fields such as `命中原因`
- operators cannot rename visible labels such as `总金额` or `门店`
- operators cannot switch between predefined message presentation styles

## Design Principles

- Keep multi-rule management intact: rules are independent and can coexist.
- Prefer reversible operational controls over destructive actions.
- Treat message format as an admin-managed global setting, not a code change.
- Keep format configuration structured and safe rather than allowing arbitrary template editing.
- Preserve the current message builder flow and only parameterize the field rendering layer.

## Feature 1: Rule Status Management

### Behavior

Rules remain independent records. Operators can:

- create multiple active rules
- disable a rule
- restore a disabled rule
- permanently delete a rule
- see each rule's current status in the rules list

Delete in this iteration means hard delete from the database.

### UI

The rules list page should add an action area for each rule:

- `停用` for enabled rules
- `删除` for enabled or disabled rules
- `恢复` for disabled rules

Status should remain clearly visible:

- `启用中`
- `已停用`

Disabled rules remain in the list and keep their summaries so operators can audit and restore them.

### Data Behavior

Use the existing `RuleGroup.is_enabled` field for active vs disabled status.

Delete behavior should permanently remove:

- the `RuleGroup` row
- all associated `RuleCondition` rows

Add dedicated status-toggle routes in the Flask app rather than overloading creation or edit actions.

Recommended behavior:

- POST route to disable a rule
- POST route to restore a disabled rule
- POST route to permanently delete a rule
- missing rule id should return a controlled error or redirect with message

## Feature 2: Global Format Management

### Behavior

Add one global format configuration that applies to generated push messages and the manual test preview.

Operators can control:

- whether a field is shown
- what label text is displayed for that field
- which preset layout style is active

The first version should manage these fields:

- order number
- store name
- sold time
- total amount
- match reason
- style number
- unit price
- barcode
- brand
- category
- image

This covers the current message structure without opening arbitrary layout editing.

### Preset Templates

Add preset templates as structured layout modes rather than raw editable markdown.

Recommended first-version presets:

- `标准版`: close to the current layout, suitable as the default
- `精简版`: shorter summary-first layout with fewer section headers
- `明细版`: emphasizes item detail visibility while keeping the same field controls

Preset templates should control:

- section ordering
- whether summary headers are dense or expanded
- how item blocks are grouped

Preset templates should not bypass field visibility settings. A field disabled in global settings stays hidden regardless of the selected preset.

### UI

Add a new admin page in navigation:

- `格式管理`

The page should have two grouped sections:

- `模板预设`
- `显示开关`
- `字段名称`

The page should expose:

- a preset selector
- a checkbox for each visible or hidden field
- a text input for each display label when applicable

Examples:

- hide `命中原因`
- rename `总金额` to `成交金额`
- rename `门店` to `店铺`
- switch from `标准版` to `精简版`

The page should show a concise note that the configuration affects both formal pushes and manual test previews.

### Persistence

Store the configuration in the database, not YAML.

Reason:

- this is an operator-managed backend setting
- it needs to be editable in the UI at any time
- database storage matches the current admin backend architecture

Recommended model shape:

- a single-row settings table for global backend settings
- one column containing serialized JSON for message format settings

This keeps the first version simple and avoids creating a separate table per field.

## Format Configuration Structure

The message format configuration should be explicit and structured.

Recommended shape:

```json
{
  "preset": "standard",
  "fields": {
    "order_no": { "enabled": true, "label": "销售单号" },
    "store_name": { "enabled": true, "label": "门店" },
    "sold_at": { "enabled": true, "label": "时间" },
    "total_amount": { "enabled": true, "label": "总金额" },
    "match_reason": { "enabled": true, "label": "命中原因" },
    "style_no": { "enabled": true, "label": "款号" },
    "unit_price": { "enabled": true, "label": "单价" },
    "barcode": { "enabled": true, "label": "条码" },
    "brand": { "enabled": true, "label": "品牌" },
    "category": { "enabled": true, "label": "品类" },
    "image": { "enabled": true, "label": "图片" }
  }
}
```

Not every field must use the label in the exact same way. For example, `image` may mainly use the enabled flag. But keeping the structure uniform simplifies storage and rendering logic.

## Message Builder Integration

The message builder should stop assuming all fields are always rendered.

Instead:

- load the active global format configuration
- load the selected preset template
- use enabled flags to decide whether a header or item field is emitted
- use configured labels when rendering field names
- use the preset to control section ordering and density

This affects:

- real push flow
- manual test preview flow

The configuration should have a default fallback so existing behavior remains stable if no settings row exists yet.

## Application Boundaries

Recommended responsibility split:

- `web_app.py`: routes, form parsing, rule status actions, format settings save and render context
- `rule_models.py`: keep rule status support and add a global settings model
- `message_builder.py`: render fields using supplied format settings and preset
- a small helper in backend code: load default format settings, normalize persisted settings, and expose preset definitions

If helper logic becomes too large, it may justify a dedicated settings helper module. If it remains small, keeping it in `web_app.py` or a focused backend helper is acceptable.

## Error Handling

Rule status management:

- invalid or missing rule id should not crash the page
- status changes should redirect back to the rules list with an error notice if needed
- deleting a rule should also delete its conditions
- delete action should require explicit confirmation in the UI to avoid accidental removal

Format management:

- malformed save payload should re-render with validation errors
- blank custom labels should either fall back to defaults or be rejected consistently
- missing settings row should transparently use defaults
- unknown preset values should fall back to the default preset or be rejected consistently

Recommended first-version behavior:

- if a label input is blank after trimming, fall back to the default label
- if preset is invalid, reject save with a validation error

## Testing Strategy

Required coverage:

- rules page shows `停用` and `删除` for active rules
- POST disable changes status to disabled
- POST restore changes a disabled rule back to enabled
- POST delete permanently removes the rule and its conditions
- format page loads default settings when nothing is stored
- format page saves updated preset, enabled flags, and labels
- message builder omits `命中原因` when that field is disabled
- message builder uses renamed labels such as `成交金额`
- message builder changes section style when a different preset is selected
- manual test preview also reflects the saved global format settings

## Recommended Rollout Order

1. Add persistence for global format settings and tests for defaults and presets
2. Add rule status routes and permanent delete behavior with tests
3. Add format management page and save behavior
4. Integrate message builder with format settings and presets
5. Verify real preview and regression tests

## Self-Review

- Scope is limited to reversible rule enable/disable management, permanent delete, and one global format configuration.
- Rule deletion is intentionally hard delete so obsolete rules do not accumulate indefinitely.
- No placeholder implementation sections remain.
- The design preserves existing multi-rule behavior while keeping format configuration global.
- Free-form template editing is intentionally excluded to avoid breaking markdown_v2 safety, while preset templates provide controlled layout variation.
