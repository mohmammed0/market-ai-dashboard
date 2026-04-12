# Market AI Dashboard — DESIGN_SPEC_PHASE1

## 1) Goal

Phase 1 is a frontend usability and visual-system overhaul for the existing web platform.

This is **not** a backend redesign.
This is **not** a product-scope expansion.
This is **not** a route restructure.

The goal is to make the existing platform feel like a premium, professional, dark trading terminal with better hierarchy, clearer actions, stronger readability, and faster workflows.

Preserve all existing route behavior and data integrations.

---

## 2) Product style direction

Visual tone:

* premium
* dark
* trading workstation
* data-dense but controlled
* minimal accent usage
* clear visual hierarchy
* calm monochrome base with semantic color only where needed

The UI should feel closer to:

* a modern market terminal
* a professional broker dashboard
* a polished quant/research workspace

Avoid:

* playful SaaS styling
* oversized cards with wasted space
* too many colors
* bright gradients
* “developer tool” look
* cluttered layouts with weak grouping

---

## 3) Core visual system

### 3.1 Color palette

Use a strict palette.

Base:

* `--bg-app: #05070A`
* `--bg-surface-1: #0B0F14`
* `--bg-surface-2: #11161D`
* `--bg-surface-3: #161C24`
* `--border-subtle: #202833`
* `--border-strong: #2B3542`

Text:

* `--text-primary: #F5F7FA`
* `--text-secondary: #A7B0BC`
* `--text-muted: #7C8794`

Semantic:

* `--accent-positive: #22C55E`
* `--accent-negative: #EF4444`
* `--accent-warning: #F59E0B`
* `--accent-info: #60A5FA`

Interaction:

* `--focus-ring: rgba(96,165,250,0.45)`
* `--hover-surface: #18202A`
* `--active-surface: #1C2632`

Rules:

* no random extra colors
* no bright blue-heavy product look
* use green/red only for market meaning, not for general decoration
* use info blue sparingly for focus, selected state, or links

### 3.2 Typography

Primary font:

* Inter, system-ui fallback

Monospace numeric font:

* ui-monospace, SFMono-Regular, Menlo, Consolas, monospace

Type scale:

* Page title: 24 / 32, weight 700
* Section title: 18 / 26, weight 600
* Card title: 14 / 20, weight 600
* Body: 13 / 20, weight 400
* Small/meta: 12 / 18, weight 500
* Large metric: 28 / 32, weight 700, monospace or tabular numeric style

Rules:

* financial numbers should use tabular alignment where possible
* labels and metadata should be visually lighter
* titles should be compact, not oversized

### 3.3 Spacing scale

Use consistent spacing:

* 4, 8, 12, 16, 20, 24, 32

Rules:

* most card padding: 16 or 20
* most page section gaps: 20 or 24
* compact tables/controls may use 8 or 12
* do not mix arbitrary spacing values unless necessary

### 3.4 Radius and shadow

* card radius: 14px
* panel radius: 16px
* small controls: 10px
* shadow: subtle only
* prefer border + contrast over heavy glow

Suggested shadow:

* `0 8px 24px rgba(0,0,0,0.22)`

---

## 4) App shell architecture

### 4.1 Overall layout

Desktop app shell:

* fixed left sidebar
* top header
* main scrollable content area
* optional right-side contextual panel only if already supported; do not add new product complexity if absent

Structure:

* Sidebar width: 248px expanded
* Compact sidebar optional later, but not required in phase 1
* Header height: 64px
* Main content max width: 1600px
* Main content padding: 20px desktop, 16px smaller screens

### 4.2 Sidebar

Sidebar should:

* feel premium and quiet
* clearly group navigation
* support icons + labels
* show active state clearly
* show section grouping if route count is high

Suggested groups:

* Overview

  * Dashboard
  * KPI Dashboard
* Market

  * Live Market / Market Explorer
  * Analyze
  * Ranking
* Trading

  * Paper Trading
  * Alerts
  * Portfolio Exposure
  * Risk
* Intelligence

  * AI News
  * Breadth
  * Strategy Lab
  * Trade Journal
  * Automation
* System

  * Settings

Sidebar styling:

* background = surface-1
* border-right = 1px subtle border
* nav item height = 40
* active item:

  * stronger surface
  * thin left indicator or inset highlight
  * brighter text
* inactive items:

  * text-secondary
  * hover-surface on hover

### 4.3 Top header

Header should include:

* current page title / page context
* optional breadcrumb or page subtitle
* top-level quick actions area on the right
* consistent alignment with content grid

Header actions may include existing actions only, for example:

* refresh
* export
* run analysis
* quick status chip
* search if already present

Do not overfill header.

### 4.4 Page shell

Every page should use a shared page shell with:

* page heading row
* optional secondary description
* action row or filter bar
* content sections beneath

Create a reusable pattern for:

* title
* subtitle
* actions
* section spacing

---

## 5) Shared reusable components to create/refactor

Create or standardize reusable components where practical:

1. `PageShell`
2. `SectionCard`
3. `MetricCard`
4. `MetricGrid`
5. `StatusBadge`
6. `ToolbarRow`
7. `FilterBar`
8. `ActionButton`
9. `DataTableShell`
10. `EmptyState`
11. `ChartCard`
12. `StatChange`
13. `SymbolBadge`
14. `PanelTitle`
15. `LoadingBlock` / `SkeletonBlock`

Do not overengineer a separate design-system package.
Keep it inside the existing frontend structure.

---

## 6) Shared component behavior

### 6.1 Cards

Cards should:

* have consistent padding
* strong title/subtitle structure
* optional top-right action slot
* subtle border
* background from surface-2 or surface-3 depending on nesting

Card anatomy:

* header row
* body
* optional footer/meta row

### 6.2 Metric cards

Metric cards should show:

* small title
* main number
* secondary note
* optional delta indicator
* optional status color only where meaningful

Good examples:

* total P/L
* CAGR
* win rate
* drawdown
* current exposure
* open positions

### 6.3 Badges

Standardize badges:

* positive
* negative
* warning
* info
* neutral

Use pills with compact height, around 24 to 28px.

### 6.4 Tables

All tables should use a shared table shell.

Rules:

* sticky header if page already benefits from it
* dark compact rows
* subtle separators
* better column spacing
* right-align numeric columns where appropriate
* monospace/tabular numbers for price, P/L, volume, percentage
* row hover state
* clickable rows visually obvious where applicable
* reduce clutter inside cells

Do not create visually loud zebra striping.

### 6.5 Forms and controls

Controls should be more consistent:

* shared input height
* shared select styling
* shared date/input/filter appearance
* clear hover/focus
* no default browser styling if current app is inconsistent

Button hierarchy:

* Primary = important page action
* Secondary = standard action
* Ghost = low emphasis
* Danger = destructive

---

## 7) Chart theming

Standardize chart styling across the app.

Look:

* dark background integrated with card
* muted grid lines
* white/light gray main series by default
* semantic green/red only when needed
* subtle tooltip
* clean axis contrast
* no bright rainbow palette

Suggested chart rules:

* grid lines low contrast
* axis text = text-muted
* tooltip = surface-1 with subtle border
* crosshair subtle
* line thickness moderate
* area fills very subtle if used
* sparkline cards allowed where already practical

If ECharts exists, centralize a theme config or helper.
If another chart library is in place, standardize equivalent theme tokens.

---

## 8) RTL and text handling

Support proper RTL compatibility where relevant.

Rules:

* prefer CSS logical properties where possible
* do not break existing LTR market tables
* ensure Arabic labels still align cleanly
* avoid hardcoded left/right when a shared utility can handle start/end
* numeric and ticker data should remain visually stable

Phase 1 does not require a full bilingual rewrite, only compatibility-safe layout work.

---

## 9) Page-by-page implementation scope

# 9.1 Dashboard

Goal:
Make Dashboard feel like a true control center.

Layout:
Row 1:

* primary summary metrics grid (4 to 6 cards)

Row 2:

* market/system overview area
* recent signals / recent activity area

Row 3:

* chart area
* watchlist snapshot / alerts / top movers depending on current app capabilities

Dashboard should emphasize:

* performance summary
* system status
* most important actions
* recent outputs
* quick understanding within 5 seconds

Requirements:

* remove cluttered arrangement
* reduce visual randomness
* improve grouping of related information
* keep key actions visible
* better spacing between data blocks

# 9.2 KPI Dashboard

Goal:
Make KPI data feel executive and analytical.

Organize into sections:

1. Performance
2. Risk
3. Strategy Quality
4. Market Intelligence
5. Benchmark / Exposure

Each section:

* section heading
* 3 to 6 metric cards
* optional supporting chart/table

Suggested KPI card emphasis:

* CAGR
* net P/L
* monthly stability
* max drawdown
* daily loss limit
* consecutive losses
* win rate
* profit factor
* expectancy
* regime performance
* best asset/market
* benchmark outperformance
* current exposure

KPI page should feel cleaner and more analytical than the main dashboard.

# 9.3 Live Market / Market Explorer

This is one of the most important pages.

Goal:
Make it feel like a professional market workspace.

Target layout:
Left / top:

* filters + universe selection + search + refresh

Main area:

* market table as the primary workspace
* clean sortable columns
* easier scanability

Side or lower detail area:

* selected symbol snapshot
* mini chart
* key stats
* quick actions to analyze / inspect / add to watchlist if already supported

Top summary strip:

* index overview
* market breadth snapshot
* movers / active names

Requirements:

* reduce page heaviness
* improve primary workspace focus
* selected symbol state should be obvious
* search/filter actions should be faster to understand
* the table must look significantly more premium and readable

# 9.4 Paper Trading

Goal:
Make the trading workflow more direct and less confusing.

Organize clearly into:

1. account summary / buying power / P&L
2. positions
3. open orders
4. signal/execution activity
5. order actions or control area if already supported

Design principles:

* separate positions from orders very clearly
* high readability for side, quantity, avg price, market price, unrealized P/L, status
* make risk-relevant info easier to see
* important actions should be obvious, not buried

If a manual paper-order path already exists, visually strengthen it.
If not, do not invent new backend functionality in this phase.

# 9.5 Settings

Goal:
Transform settings into a clean system configuration page.

Group settings into clear sections:

1. System
2. Runtime / scheduler
3. OpenAI
4. Broker
5. API / environment status

Each section should:

* have a heading
* short explanatory text
* grouped controls or status display
* better spacing and clearer separators

Requirements:

* no cluttered wall of settings
* make statuses easy to scan
* make sensitive config clearly separated from informational values
* support a “control center” feel, not a raw developer panel

---

## 10) Information hierarchy rules

Across all pages:

Primary content:

* large metrics
* core tables
* main charts
* high-value actions

Secondary content:

* metadata
* descriptions
* helper notes
* timestamps
* system labels

Rules:

* never let metadata compete with main metrics
* use muted text aggressively for low-priority info
* align actions consistently
* avoid too many equal-weight blocks on the same page

---

## 11) Responsive behavior

Phase 1 should improve responsiveness without redesigning mobile from scratch.

Desktop first.
Tablet safe.
Basic smaller-width tolerance.

Rules:

* sidebar can remain persistent on larger screens
* on narrower screens, ensure content stacks more cleanly
* metric grids should collapse gracefully
* table overflow should remain usable
* header/actions should wrap cleanly, not break layout

---

## 12) CSS / styling implementation expectations

Codify tokens centrally.
Refactor scattered styles into a cleaner shared styling pattern.

Preferred implementation:

* central theme/tokens file
* shared layout primitives
* reusable card/table/control styles
* page-specific styles only where needed

Do not rewrite the entire styling stack if unnecessary.
Do the minimum necessary to create consistency.

---

## 13) Accessibility and usability expectations

* maintain readable contrast
* visible focus states
* buttons/controls should not rely on color only
* status differences should be readable at a glance
* do not reduce text size too far for dense screens
* use hover states subtly but clearly

---

## 14) Phase 1 boundaries

Do:

* frontend layout cleanup
* reusable components
* style standardization
* page hierarchy improvements
* chart theme consistency
* table readability improvements
* settings organization
* workflow clarity improvements

Do not:

* introduce a new routing model
* redesign backend architecture
* add large new features
* touch desktop UI
* change core API contracts unless a tiny additive compatibility fix is required
* perform broad refactors unrelated to UI/usability

---

## 15) Execution order

Implement in this order:

1. foundation

* tokens
* shared primitives
* shell
* buttons
* cards
* table shell
* badges
* chart theme

2. page shell integration

* shared page layout
* title/action/filter patterns

3. Dashboard

4. KPI Dashboard

5. Live Market / Market Explorer

6. Paper Trading

7. Settings

8. final polish

* spacing consistency
* hover/focus states
* empty/loading states
* responsive cleanup

---

## 16) Validation requirements

Before stopping:

1. `npm run build` passes
2. no blank pages
3. target routes render
4. data tables still function
5. charts still render
6. no existing core workflows are broken
7. shared components are actually reused, not just duplicated styling

---

## 17) Required report format

When done, report only:

1. exact files changed
2. reusable primitives/components created or standardized
3. exact shell/layout changes
4. exact improvements for:

   * Dashboard
   * KPI Dashboard
   * Live Market / Market Explorer
   * Paper Trading
   * Settings
5. whether `npm run build` passes
6. whether the main routes render
7. any remaining phase 2 usability gaps

This spec is the source of truth for phase 1.
If current code constraints require small interpretation decisions, choose the option that best preserves functionality while moving toward this design direction.
