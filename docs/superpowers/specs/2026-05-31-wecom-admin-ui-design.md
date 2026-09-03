# WeCom Sales Webhook Bot Admin UI Design

## Goal

Improve the existing Flask admin backend into a more usable Chinese-language management console before integrating the real IT API. This iteration focuses on clearer navigation, denser rule visibility, better form feedback, and a visible manual test entry point that prepares the later `CSV + local image URL` verification flow.

## Scope

This design covers these pages:

- `login.html`
- `rules.html`
- `rule_edit.html`
- `push_records.html`
- `system_status.html`
- a new manual test page and route

This design does not cover:

- real IT API integration
- replacing the current rule persistence model
- changing the local compatibility edits already present in `cli.py`, `csv_source.py`, and `orchestrator.py`
- wiring the full `CSV + local image URL` execution flow in this same step

## Current Context

The current backend is already functional but minimal:

- login works
- rules can be created
- push records can be viewed
- system status can be viewed

The main gaps are usability and operator clarity:

- the templates are skeletal
- navigation is weak
- failed login has no visible feedback
- rule list content is too sparse for daily use
- rule conditions are persisted but not summarized well in the UI
- there is no explicit manual test page for the upcoming CSV-based verification workflow

## Design Principles

- Keep the backend simple and server-rendered.
- Improve operator efficiency before adding deeper workflow logic.
- Prefer richer page context from Python over complex Jinja template logic.
- Preserve compatibility with the current data model and local test setup.
- Make empty states and failure states explicit in Chinese.

## Information Architecture

The admin backend should behave like a compact internal console.

Primary navigation:

- `规则管理`
- `新建规则`
- `手动测试`
- `推送记录`
- `系统状态`

Default post-login landing page:

- `规则管理`

The manual test page should exist in navigation in this iteration even if it only provides a structured placeholder for the next task.

## Page Designs

### Login Page

Purpose:

- provide a clean, focused entry point for internal operators
- make login failure visible instead of silently redirecting back

Behavior:

- show product title and concise subtitle
- show username and password fields
- show inline Chinese error text after failed login
- keep layout narrow and distraction-free

### Rule List Page

Purpose:

- act as the main operating dashboard
- let the operator scan rule status and rule intent quickly

Behavior:

- show page title and concise operational description
- show prominent `新建规则` action
- show each rule as a readable card or dense row block
- show enabled/disabled status
- show `any` / `all` in operator-friendly Chinese wording
- show updater and update time
- show a Chinese condition summary generated on the server side
- show an explicit empty state when no rules exist

Condition summary format should prefer short readable labels such as:

- `金额 >= 10000`
- `款号: PA17047BNY0, PA15161ENY0`
- `门店: G621, G609`
- `时段: 10:00-18:00`
- `品牌: Brand-A, Brand-B`
- `品类: 外套, 连衣裙`

### Rule Create Page

Purpose:

- make rule creation understandable without reading code or database structure

Behavior:

- split the form into `基础信息` and `筛选条件`
- keep current save semantics and field names compatible with existing POST handling
- add short helper text and examples for comma-separated fields
- display clear Chinese labels for match mode
- preserve checkbox-based enable state
- surface validation errors in-page when required fields are missing or malformed

### Push Records Page

Purpose:

- let operators inspect the latest push results quickly

Behavior:

- show most recent records first
- highlight order number, store, amount, rule name, status, timestamp
- show failure reason only when present
- show empty state when no push history exists
- render status with clear visual distinction for success and failure

### System Status Page

Purpose:

- summarize the latest scan execution health

Behavior:

- show latest run timestamp
- show scan window start and end
- show execution status
- show success and failure counts
- show error summary when present
- show a useful empty state when no job has run yet

### Manual Test Page

Purpose:

- establish a clear operator entry point for the next phase of local CSV verification

Behavior in this iteration:

- page is reachable from navigation
- page explains that it will be used for `CSV + local image URL` verification
- page contains a structured placeholder area for future input form and result panel
- page makes clear that real IT API access is not part of the current flow

## Backend View-Model Changes

The Flask app should provide richer render context rather than pushing presentation logic into templates.

Planned additions in `web_app.py`:

- shared navigation metadata
- per-page title metadata
- login error flag or message
- server-side rule summaries derived from `RuleCondition`
- operator-friendly status text for rules, records, and latest run

Recommended helper responsibilities:

- summarize stored conditions into compact Chinese labels
- translate `match_mode` from persistence values into display text
- normalize empty collections into explicit empty states

These helpers can stay inside `web_app.py` if they remain small and focused.

## Error Handling

- failed login should return the login page with a visible error message
- invalid rule form submission should keep the user on the form and show a Chinese error summary
- pages with no records or no status data should show deliberate empty-state text rather than blank sections

## Testing Strategy

This design should be implemented test-first around the current Flask app tests.

Required coverage additions:

- failed login shows visible error text
- authenticated navigation can reach the new manual test page
- rule creation redirects or re-renders correctly and rule list shows status plus condition summary
- rules page shows meaningful empty state when no rules exist
- status page renders both empty-state and populated-state content
- records page renders empty-state and record rows

## Visual Direction

The UI should remain simple HTML templates, but it should no longer feel like scaffolding.

Visual direction:

- clean Chinese internal tool aesthetic
- stronger spacing and section hierarchy
- card or panel structure instead of raw stacked text
- restrained colors with clear status contrast
- desktop-first readability with acceptable mobile fallback

This should be implemented with lightweight template CSS embedded in the shared base layout unless the existing project structure justifies a separate static stylesheet.

## Implementation Boundary For Next Step

The next implementation pass should stop after:

- upgraded admin templates
- updated Flask routes and page context
- new manual test page skeleton
- expanded web app tests for the new UX behavior

The next implementation pass should not yet claim that the full `CSV + local image URL` manual test workflow is complete.

## Self-Review

- No placeholder sections remain.
- Scope is limited to a single implementation pass focused on UI and route behavior.
- The design is consistent with the current Flask architecture and the handoff constraint to preserve local compatibility edits.
