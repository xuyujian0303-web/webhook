# WeCom Global Markdown Template Management Design

## Goal

Replace the current structured field-toggle format management with a more open global message template system that remains safe for WeCom `markdown_v2` delivery.

The new system should let operators:

- edit one global `markdown_v2` template directly
- control field order, labels, headings, and emphasis through template text
- preview the rendered result against a fixed sample order
- start from built-in preset templates without creating multiple saved template slots

This design keeps message configuration globally managed while moving from rigid field switches to a template-first model.

## Scope

This design covers:

- replacing the current format-management UI with a template editor workspace
- defining a safe first-version template syntax
- adding built-in preset templates for quick initialization
- providing preview rendering with fixed sample data
- saving one global template configuration in the database
- making manual test preview and real push rendering use the same template engine

This design does not cover:

- multiple saved user templates
- directory-loaded custom template files
- loops or conditionals in template syntax
- true rich text or arbitrary font size control
- WYSIWYG editing

## Current Context

The current backend already supports:

- rule management and manual test execution
- one global message-format record in the database
- message generation through `build_markdown_v2_message`
- manual-test preview using the same push pipeline

The current gaps are now product and extensibility related:

- preset names such as `standard`, `compact`, and `detailed` are only thin layout modes, not truly open templates
- operators still cannot edit the full message body directly
- field order and textual structure are mostly code-driven
- the current configuration model is not a good fit for open-source-style customization

## Design Principles

- Keep one global template only. This is an operator-managed deployment setting, not a library of saved templates.
- Prefer explicit text templates over hidden code-controlled layouts.
- Keep the syntax intentionally small so rendering and validation stay reliable.
- Make preview rendering and real delivery share the same engine.
- Avoid presenting UI options that WeCom cannot actually render.

## WeCom Formatting Boundary

The delivery target is WeCom `markdown_v2`, not generic GitHub Markdown.

The design should therefore assume:

- a constrained markdown dialect
- byte-length limits on message payload
- support for heading-like structure, emphasis, block quotes, code formatting, and image links only insofar as the current push format already uses them safely

The design must not promise:

- arbitrary font size
- CSS-like styling
- unsupported markdown extensions

In first version, "size" is expressed only indirectly through markdown structure such as:

- `#`
- `##`
- `**bold**`
- block quote lines

## Product Direction

The existing format-management page should become a message template workspace.

Operators will manage one global template that contains the entire message body as text. Built-in presets remain available, but only as starting points that can overwrite the editor contents before saving.

The result is:

- one saved template
- several system presets
- no independent preset-specific saved slots

## Feature 1: Global Template Workspace

### Behavior

The admin UI should provide one page for editing the global template.

Operators can:

- select a built-in preset
- load that preset text into the editor
- edit the full template body directly
- preview the rendered result
- save the current template
- restore the last saved version from the database

Selecting a preset alone should not persist anything. Only explicit save writes the new template.

### UI Layout

The page should be a single workspace with four areas:

- top toolbar
- left editor panel
- right preview panel
- bottom reference panel

#### Top Toolbar

Actions:

- preset selector
- `加载预设`
- `保存模板`
- `恢复已保存版本`

#### Left Editor Panel

Contains:

- template name input or readonly name display
- large text editor for `markdown_v2` body

The first version can use a plain textarea. A code editor widget is optional later.

#### Right Preview Panel

Shows:

- rendered preview text
- optional byte-length indicator
- validation messages if rendering fails

Preview uses fixed sample data and should be refreshed on demand. First version does not require per-keystroke live rendering.

#### Bottom Reference Panel

Shows:

- available variables
- available filters
- `items_markdown` usage note
- built-in example snippet

## Feature 2: Built-In Preset Templates

### Behavior

Presets remain useful, but only as bundled template texts.

First-version preset keys:

- `standard`
- `compact`
- `detailed`

Each preset corresponds to a complete template body string. Loading one preset replaces the editor content with that preset text.

### Meaning

Presets are not:

- separate saved configurations
- alternate live rendering modes
- multiple persistent template slots

Presets are:

- initialization sources
- examples of supported syntax
- quick starting points for operators

## Feature 3: Template Syntax

### Supported Syntax

The first version supports only three concepts:

1. Plain text markdown content
2. Variable placeholders
3. A single built-in item block placeholder

### Variable Syntax

Use double-curly syntax:

```md
{{ order.order_no }}
{{ order.store_name }}
{{ order.sold_at | datetime }}
{{ order.total_amount | money }}
```

### Built-In Item Block

Only one item-list placeholder is supported:

```md
{{ items_markdown }}
```

This placeholder expands to a fully formatted markdown fragment built by backend code. It is intentionally not user-loopable.

### Unsupported Syntax

Do not support:

- loops
- conditionals
- arbitrary function calls
- nested template blocks
- HTML

Examples of unsupported syntax:

```md
{{#items}} ... {{/items}}
{{ if order.total_amount > 1000 }}
{{ custom_fn(order.order_no) }}
```

## Feature 4: Filters

The first version supports a very small filter set:

- `money`
- `datetime`

Examples:

```md
{{ order.total_amount | money }}
{{ order.sold_at | datetime }}
```

Filter behavior:

- `money` renders numeric values with a stable currency-like decimal format such as `21500.00`
- `datetime` renders order time in the established display format such as `2026-06-05 10:50:00`

No user-defined filters are allowed.

## Template Data Model

Store the new template configuration under a new global setting key such as `message_template`.

Recommended JSON shape:

```json
{
  "template_name": "自定义模板",
  "template_body": "# 零售晒单\n## 成交摘要\n> **销售单号**：`{{ order.order_no }}`\n\n{{ items_markdown }}",
  "preset_key": "standard"
}
```

Field meaning:

- `template_name`: display name for the saved global template
- `template_body`: the only field that actually drives rendering
- `preset_key`: informational origin marker only

`preset_key` must not be treated as a separate rendering source after save.

## Preview Data

Preview should use one fixed built-in sample order.

Recommended characteristics:

- one matched order
- multiple items
- image URLs present
- brand and category present
- high total amount

This ensures preview covers most formatting cases without depending on the latest manual test run.

Preview data should be generated in backend code, not loaded from the database or session state.

## Rendering Architecture

The current message formatting logic should be refactored into a template-driven pipeline.

Recommended component split:

### `message_template_defaults.py`

Responsibilities:

- store built-in preset template bodies
- expose preset labels and contents

### `message_template_schema.py`

Responsibilities:

- define allowed variable names
- define allowed filters
- provide help text for the template reference panel

### `message_template_engine.py`

Responsibilities:

- parse `{{ ... }}`
- resolve variables from context
- apply supported filters
- inject `items_markdown`
- validate unknown variables and filters
- return rendered text plus validation results and byte length

### `message_template_service.py`

Responsibilities:

- load current saved template from database
- initialize defaults when missing
- save validated template payload
- provide preview sample data

### Existing Integrations

- `web_app.py` should handle routes, forms, and workspace rendering
- `message_builder.py` should become a context-preparation layer that delegates to the template engine
- manual test preview and formal push paths should both call the same rendering flow

## Validation Rules

Saving a template should validate at minimum:

- template body is not blank
- all variables are in the allowlist
- all filters are in the allowlist
- `items_markdown` is used as a standalone placeholder and not with unsupported filters
- rendered output is within or clearly near the WeCom payload limit

Validation errors should be explicit and operator-friendly:

- unknown variable name
- unknown filter name
- malformed placeholder
- rendered message too large

If possible, error reporting should include the problematic token text.

## Migration Strategy

This change should be introduced through compatibility migration rather than destructive replacement.

### New Primary Setting

Add a new global setting key:

- `message_template`

### Existing Setting

Keep the existing:

- `message_format`

for compatibility during rollout, but stop using it as the primary rendering source once `message_template` exists.

### Initialization

If `message_template` does not exist:

- initialize it from the built-in `standard` preset on first access

This avoids forcing a data migration step before startup.

### Post-Migration Behavior

- template workspace reads and saves `message_template`
- manual test preview reads `message_template`
- formal push rendering reads `message_template`
- old field-toggle UI is removed

Cleanup of obsolete `message_format` rows can be deferred to a later maintenance change.

## Testing Strategy

Required coverage:

- template service initializes default saved template when none exists
- built-in presets load expected body text
- template engine resolves allowed variables
- template engine applies `money` and `datetime` filters
- template engine rejects unknown variables
- template engine rejects unknown filters
- template engine renders `items_markdown`
- workspace page loads saved template
- loading preset updates editor state without persisting until save
- save persists template body
- restore reloads saved template
- preview page shows rendered result from fixed sample order
- manual test flow uses saved template
- real message build path uses saved template

## Recommended Rollout Order

1. Add template defaults, schema, and engine with tests
2. Add template persistence service and default initialization
3. Replace format-management page with template workspace
4. Add preview rendering with fixed sample data
5. Switch manual test and real message generation to the template engine
6. Run regression tests across web, message, and orchestrator paths

## Self-Review

- Scope is intentionally limited to one global template and built-in presets.
- The design is explicit that WeCom formatting is constrained and not arbitrary Markdown or CSS.
- No part of the design assumes multiple saved templates or loop syntax.
- Preview and actual delivery are required to share one rendering engine, avoiding divergence.
- Migration is backward-compatible and does not require immediate cleanup of older settings data.
