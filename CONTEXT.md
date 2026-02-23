# Project Context: pioj

## Overview

**pioj** ("Personal Instance of JIRA") is a self-hosted web app for creating alternative dashboard views of JIRA work items. It provides custom workstream organization, multiple view modes, and better performance than native JIRA dashboards.

**Tech Stack:**
- Backend: Flask (Python) with JIRA REST API v2
- Frontend: Vanilla JavaScript with HTML/CSS (no frameworks)
- Package Manager: `uv`
- Data Storage: Server-side JSON file (`workstreams.json`)

## Architecture

### Backend (server.py)

**Flask Server** running on `http://localhost:5000`

**Key Endpoints:**
- `GET /` - Serves index.html
- `GET /api/config/status` - Check JIRA configuration status
- `GET /api/workstreams` - Load workstreams from workstreams.json
- `POST /api/workstreams` - Save workstreams (creates backups, keeps last 5)
- `POST /api/search` - Search JIRA issues via JQL
- `GET /api/issue/<issue_key>` - Fetch individual issue

**Authentication:**
- Cloud JIRA: Basic Auth (email + token)
- Server/Data Center: Bearer token (no email)
- Configured via `.env` file (JIRA_HOST, JIRA_EMAIL, JIRA_TOKEN)

**Important Implementation Details:**

1. **Custom Fields:**
   - Dynamically looks up custom field IDs by name at runtime
   - Caches field mappings to avoid repeated API calls
   - Works across different JIRA instances without hardcoded field IDs

   **Estimation Field (Story Points/T-Shirt Size):**
   - Supports multiple estimation systems: numeric (story points), string (t-shirt sizes), or custom
   - Three-tier lookup strategy:
     1. Optional `JIRA_ESTIMATION_FIELD` env var for custom field names
     2. Automatic fallback to common names: "Story point estimate", "Story Points", "Points", "Estimate", "T-Shirt Size", "Size", etc.
     3. Smart value handling: numeric (int/float), string (XS/S/M/L/XL), or objects

   **Epic/Parent Hierarchy:**
   - Supports both JIRA Cloud native hierarchies and Server/Data Center custom fields:
     - JIRA Cloud: Uses standard `parent` field, detects Epic by issuetype
     - JIRA Server/Data Center: Uses "Epic Link" and "Parent Link" custom fields
     - When parent is an Epic, populates both epic and parent fields for full compatibility

2. **Performance Optimization:**
   - Only fetches changelog for tickets in "In Progress" or "Review" status
   - This avoids hitting API rate limits and improves response time
   - Changelog is used to show "since" duration

3. **Epic/Parent Summary Fetching:**
   - After initial query, makes individual requests for epic/parent summaries
   - Caches results to avoid duplicate fetches
   - Updates all tickets with resolved names

### Frontend (index.html)

**Single-page application** with no build step or dependencies.

**Data Model:**
```javascript
{
  pages: [
    {
      id: string,
      name: string,
      workstreams: [
        {
          id: string,
          name: string,
          jql: string,
          lastRefresh: timestamp,
          tickets: [...],
          groupBy: 'none'|'epic'|'parent'|'assignee',
          viewMode: 'cards'|'table'|'tree'
        }
      ]
    }
  ],
  activePageId: string
}
```

**View Modes:**
1. **Cards** - Kanban board with status columns (New/In Progress/Review/Done)
2. **Table** - Spreadsheet-style sortable table
3. **Tree** - Hierarchical view showing epics → stories → subtasks → links

All views show sprint information for tickets in active or upcoming sprints (omitted for closed/past sprints).

**Theme System:**
- Light/Dark mode toggle with localStorage persistence
- CSS variables for all colors (--bg-primary, --text-primary, --color-primary, etc.)
- Icon: 🌙 for light mode, ☀️ for dark mode

**Status Categories:**
- `new` - To Do, Open, Backlog
- `indeterminate` - In Progress, In Review, etc.
- `done` - Done, Closed, Resolved
- Custom: `review` - Any status with "review" in name

## Key Features

### 1. Pages/Tabs
- Organize workstreams into different pages (by sprint, team, project)
- Create with "+ New Page", delete with "×" button
- Rename by double-clicking the page name (inline editing)
- Cannot delete last page

### 2. Workstreams
- Define via JQL queries OR comma-separated ticket keys
- Refresh individual or all at once
- Shows "Last updated: X ago" timestamp
- Can group by Epic, Parent Link, or Assignee (disabled in tree view)
- Quick navigation badges show ticket count (including 0 for empty workstreams)

### 3. Tree View
- Auto-deduplication: each ticket appears once even if referenced multiple times
- Shows hierarchy: epics → stories → subtasks → linked issues
- Icons: 🚀 Epic, 📖 Story, 🐛 Bug, ✓ Task, 🔗 Link
- Tickets not in main query are shown in grey italics

### 4. "Since" Duration
- For tickets in Progress or Review status
- Shows how long ticket has been in current state
- Format: "Since Xm" / "Xh" / "Xd" / "Xmo"
- Calculated from changelog API

### 5. Export/Import
- **Export Config**: Download JSON with pages/workstreams structure (no ticket data)
- **Import Config**: Replace or Merge modes
- **Export CSV**: Download ticket data as spreadsheet

## File Structure

```
/home/michael/tmp/workstreams/
├── server.py              # Flask backend
├── index.html             # Frontend SPA
├── jira-workstreams.html  # (unused, legacy?)
├── main.py                # (unused?)
├── README.md              # User documentation
├── CONTEXT.md             # This file
├── LICENSE                # MIT License
├── .env                   # JIRA credentials (gitignored)
├── .env.example           # Template for .env
├── workstreams.json       # Server-side data storage (gitignored)
├── workstreams_backup_*.json  # Auto-backups (gitignored)
├── pyproject.toml         # Python dependencies
├── uv.lock                # Locked dependencies
└── requirements.txt       # Pip format dependencies
```

## Important Patterns & Conventions

### 1. Never Over-Engineer
- Keep solutions minimal and focused
- Don't add features beyond what's requested
- Avoid premature abstractions

### 2. CSS Variables for Theming
- All colors must use CSS variables
- Never hardcode colors, borders, or shadows
- Variables defined in `:root` and `body.dark-mode`

### 3. Error Handling
- Backend: Try-except with JSON error responses
- Frontend: Show alerts for user-facing errors
- Graceful degradation (e.g., skip changelog if fetch fails)

### 4. State Management
- workstreams.json is source of truth
- Frontend loads from server on startup
- Auto-save on every change
- LocalStorage only for theme preference

### 5. JIRA API Quirks
- Cannot use `expand=changelog` in search endpoint (causes 400 error)
- Must fetch changelog separately for individual issues
- Custom field IDs vary by JIRA instance - dynamically looked up by name via `/rest/api/2/field`
- Use `statusCategory.key` not status name for categorization

## Development Workflow

1. **Install dependencies**: `uv install`
2. **Configure JIRA**: Copy `.env.example` to `.env` and fill in credentials
3. **Run server**: `uv run server.py`
4. **Open browser**: http://localhost:5000
5. **No build step required** - just edit and refresh

## Known Gotchas

1. **PDM Legacy**: Project migrated from `pdm` to `uv`, `.pdm-python` file should be ignored
2. **Port 5000**: Make sure nothing else is using port 5000
3. **JIRA Email**: Must be empty for Server/Data Center, required for Cloud
4. **Max Results**: Search limited to 100 tickets per workstream
5. **Custom Fields**: Looks up by name ("Story Points", "Epic Link", "Parent Link") - works across JIRA instances
6. **Browser Support**: Uses modern JS (fetch, arrow functions, template literals) - needs modern browser

## Security Notes

- Credentials only sent to localhost Flask server
- No external services or analytics
- `.env` and `workstreams.json` excluded from git
- API tokens should have minimal required permissions

## Future Considerations

If expanding this project:
- Custom field configuration UI (instead of hardcoding)
- Pagination for >100 tickets
- Real-time updates via polling/webhooks
- Multi-user support with authentication
- Docker containerization
- Custom board layouts beyond standard columns
