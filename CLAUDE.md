# Claude Guide for pioj

## Quick Reference

**pioj** is a self-hosted JIRA dashboard web app with custom workstream organization.

**Tech Stack:** Flask backend + vanilla JavaScript frontend (no frameworks/build step)

**Run:** `uv run server.py` → http://localhost:5000

**Optional:** LLM integration for AI summaries (OpenAI-compatible API)

## Critical Patterns

### 1. Minimal Changes Only
- Never add features beyond what's requested
- Don't refactor surrounding code
- Don't add comments, docstrings, or type hints to unchanged code
- Keep solutions simple and focused

### 2. CSS Theming
- **ALWAYS** use CSS variables for colors, borders, shadows
- **NEVER** hardcode color values
- Variables are defined in `:root` and `body.dark-mode`
- Theme toggle persists to localStorage

### 3. Caching System

**cache.json File:**
- Stores full ticket details (changelog + comments) to reduce API calls
- Cache expiry: 1 hour (CACHE_EXPIRY_HOURS)
- Full data cached, filtered by date range on retrieval
- Check `get_cached_ticket_details()` in server.py

**Key Pattern:**
```python
# Stores FULL changelog/comments
# Filters by date range when requested
filtered_data = filter_ticket_data_by_date(cached_data, days)
```

### 4. JIRA API Handling

**Custom Fields:**
- Field IDs vary by instance - look up by name at runtime
- Cached in memory to avoid repeated API calls
- See `get_custom_field_id()` in server.py

**Estimation Field:**
- Three-tier lookup: env var → common names → fallback
- Handles numeric (story points), string (T-shirt), or custom
- Common names: "Story point estimate", "Story Points", "Points", "T-Shirt Size", etc.

**Sprint Field:**
- Supports JIRA_SPRINT_FIELD env var for custom sprint field names
- Parses sprint state (active, future, closed)
- Handles both string and object formats

**Epic/Parent Hierarchy:**
- Cloud: Uses `parent` field, detects Epic by issuetype
- Server/Data Center: Uses "Epic Link" and "Parent Link" custom fields
- Dual population for compatibility

**Performance:**
- Only fetch changelog for "In Progress" or "Review" tickets
- Cannot use `expand=changelog` in search (causes 400 error)
- Must fetch changelog separately per issue
- Use caching to minimize API calls

### 5. Query Stacking (Advanced JQL)

**Feature:** Build complex queries by stacking and combining results

**Query Types:**

1. **Basic JQL** - Standard JIRA query
2. **FOREACH** - Iterate over previous query results with placeholders:
   - `{issue}` - Current issue key
   - `{epic}` - Epic key
   - `{parent}` - Parent key
   - `{assignee}` - Assignee name (quoted)
   - `{reporter}` - Reporter name (quoted)
   - Example: `FOREACH {query1}: issuekey in childissuesof({issue})`

3. **Set Operations** - Combine query results:
   - `UNION` - All tickets from both queries
   - `INTERSECT` - Only tickets in both queries
   - `SUBTRACT` - Tickets in first but not second
   - `XOR` - Tickets in one or the other, but not both
   - Example: `{query1} UNION {query2}`

**Modal Queries:**
- `modalQueries` array holds temporary state during editing
- Only applied when user confirms in modal
- Not saved until user clicks "Apply" or "Add Workstream"

### 6. LLM Integration (Optional)

**AI Summary Feature:**
- Summarizes ticket changes/comments over time period
- Uses OpenAI-compatible API (supports custom base URLs)
- Configuration in `.env`:
  - `LLM_API_KEY` - API key (required)
  - `LLM_API_BASE` - Custom base URL (optional, defaults to OpenAI)
  - `LLM_MODEL` - Model name (default: gpt-4o-mini)

**Endpoint:** `POST /api/workstream/summary`
**Features:**
- Filter by days (e.g., last 7 days)
- Optional context input for custom instructions
- Omit inactive tickets (no changes/comments)
- Uses cached ticket details to minimize API calls

### 7. State Management
- `workstreams.json` is source of truth (server-side)
- Auto-save on every frontend change via POST to `/api/workstreams`
- Auto-backups created, keeps last 5
- LocalStorage only for theme preference and emergency backup

### 8. Data Model

**Workstreams Structure:**
```javascript
{
  pages: [{
    id: string,
    name: string,
    workstreams: [{
      id: string,
      name: string,
      jql: string,          // Can be basic JQL or query stack
      queries: [...],       // Query stack (if using advanced queries)
      tickets: [...],
      groupBy: 'none'|'epic'|'parent'|'assignee',
      viewMode: 'cards'|'table'|'tree',
      summary: {            // Optional AI summary
        text: string,
        days: number,
        generatedAt: timestamp
      }
    }]
  }],
  activePageId: string
}
```

**Query Stack Item:**
```javascript
{
  name: string,
  type: 'JQL' | 'FOREACH' | 'SET_OPERATION',
  jql: string
}
```

## API Endpoints

**Core Endpoints:**
- `GET /` - Serve index.html
- `GET /api/config/status` - Check JIRA/LLM configuration
- `GET /api/workstreams` - Load workstreams from file
- `POST /api/workstreams` - Save workstreams (with backup)
- `POST /api/search` - Search JIRA via JQL
- `GET /api/issue/<issue_key>` - Fetch individual issue

**Advanced Endpoints:**
- `POST /api/ticket/details` - Get ticket details with changelog/comments (uses cache)
- `POST /api/workstream/export` - Export workstream as markdown
- `POST /api/workstream/summary` - Generate AI summary (requires LLM config)

## View Modes

**Cards:** Kanban board with status columns (New/In Progress/Review/Done)
**Table:** Sortable spreadsheet view
**Tree:** Hierarchical epic → story → subtask → links with auto-deduplication

## Common Tasks

### Adding a Feature
1. Read relevant files first (server.py and/or index.html)
2. Understand existing patterns
3. Make minimal changes
4. Use CSS variables for any styling
5. Test with `uv run server.py`

### Modifying JIRA Integration
- Check `get_custom_field_id()` for field lookup pattern
- Use `statusCategory.key` not status name
- Remember Cloud vs Server/Data Center differences
- Consider caching - check `get_cached_ticket_details()` pattern
- Avoid rate limiting by using cache.json

### Working with Query Stacking
- Queries are processed sequentially (query1, then query2, etc.)
- FOREACH placeholders replaced per result from previous query
- Set operations use JIRA's native `issue in (key1, key2)` for combining results
- Modal editing uses temporary `modalQueries` array
- Validate JQL before execution to avoid API errors

### Page Management
- Create pages via "+ New Page" button (opens modal)
- Rename pages by double-clicking the tab name (inline editing)
- Delete pages with "×" button (cannot delete last page)
- Switch pages by clicking tab
- All changes auto-save to server

### Frontend Changes
- No build step - edit index.html directly
- Use vanilla JavaScript (no frameworks)
- Maintain theme variable usage
- Auto-save triggers on data changes
- Modal state in temporary variables (e.g., `modalQueries`)
- Inline editing pattern: replace element with input, handle blur/Enter/Escape

## File Structure

```
server.py              # Flask backend (JIRA API, endpoints)
index.html             # Frontend SPA (all JS/HTML/CSS)
workstreams.json       # Server-side data storage (gitignored)
cache.json             # Ticket details cache (gitignored)
.env                   # JIRA/LLM credentials (gitignored)
.env.example           # Template for configuration
workstreams_backup_*.json  # Auto-backups (gitignored, keeps last 5)
```

## Configuration

**JIRA Settings (.env):**

Cloud JIRA: Email + Token
Server/Data Center: Bearer token only (no email)

```bash
# Required
JIRA_HOST=https://your-instance.atlassian.net
JIRA_TOKEN=your_token
JIRA_EMAIL=your@email.com  # Empty for Server/DC

# Optional - Custom field overrides
JIRA_ESTIMATION_FIELD=Custom Field Name
JIRA_SPRINT_FIELD=Custom Sprint Field
```

**LLM Settings (.env) - Optional for AI summaries:**
```bash
LLM_API_KEY=your_api_key
LLM_API_BASE=https://api.openai.com/v1  # Optional, defaults to OpenAI
LLM_MODEL=gpt-4o-mini  # Optional, defaults to gpt-4o-mini
```

## Error Handling

**Backend:** Try-except with JSON error responses
**Frontend:** Alert for user errors, graceful degradation for optional features

## Important Constants

**Backend (server.py):**
```python
WORKSTREAMS_FILE = 'workstreams.json'
CACHE_FILE = 'cache.json'
CACHE_EXPIRY_HOURS = 1
```

**Frontend (index.html):**
```javascript
const API_BASE = '/api'
let data = { pages: [...], activePageId: ... }  # Global state
let modalQueries = []  # Temporary query editing state
```

## Status Categories

- `new` → To Do, Open, Backlog
- `indeterminate` → In Progress
- `review` → Any status with "review" in name
- `done` → Done, Closed, Resolved

Use `statusCategory.key` from JIRA API.

## Tree View Specifics

- Auto-deduplicates tickets (each appears once)
- Shows hierarchy with icons: 🚀 Epic, 📖 Story, 🐛 Bug, ✓ Task, 🔗 Link
- Grey italics for tickets outside main query
- GroupBy disabled in tree view

## Key Constraints

- Max 100 tickets per workstream search (per individual JQL query)
- Cannot delete last page
- Cache expiry: 1 hour (affects ticket details, changelog, comments)
- Modern browser required (fetch, arrow functions, template literals)
- Runs on localhost:5000 only
- Query stacking executes sequentially (not parallel)
- LLM integration requires OpenAI-compatible API

## Backward Compatibility

- `migrateWorkstream()` handles legacy data formats
- Old operation types (UNION, INTERSECT, etc.) migrated to SET_OPERATION
- LocalStorage used as emergency backup if server unavailable
- Check git history for migration patterns before breaking changes

## Security

- No external services (except JIRA API and optional LLM API)
- Credentials only sent to localhost Flask server
- `.env`, `workstreams.json`, and `cache.json` gitignored
- Use minimal JIRA token permissions
- LLM API key stored in .env (never exposed to frontend)

## Maintaining This Guide

**IMPORTANT:** When making significant changes to the project, update CLAUDE.md:

- New features → Add to relevant sections
- New API endpoints → Update "API Endpoints" section
- New environment variables → Update "Configuration" section
- New patterns or conventions → Add to "Critical Patterns"
- Breaking changes → Update "Backward Compatibility"
- New files → Update "File Structure"

Keep the guide concise and actionable. Focus on what an AI assistant needs to know to make changes correctly.
