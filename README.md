# pioj

pioj - "Personal Instance of JIRA" :D

Don't believe the name, it's not a personal instance of JIRA (it comes from a
joke when a colleague first saw this tool in its early phases).

This tool is a simple web app you can self host on your machine to provide
alternative dashboard views of your JIRA work items. You might ask, why you
need such a thing when you can directly create boards and filters in JIRA
itself? Here's some potential reasons:

1. You might need to create some data views that you don't want public or
   viewable by others (example: tracking tickets per team member)
2. Your JIRA instance is slow so anytime you load the dashboard, you wait five
   minutes. With this, the data is loaded once and kept cached until you decide
   to refresh it.
3. You want to put multiple views onto one page without doing the hard work of
   setting up a dashboard and maintaining a bunch of associated rich filters.
4. You want a tree view of dependencies/blockers (hard to get in basic JIRA).
5. You want to do some subqueries or interact with queries using set notation.
6. You want a markdown export of your tickets to use for A.I. processing.
7. You want to keep your magic JIRA understanding to yourself and not share it.

## Features

### Core Features

- 📄 **Multiple Pages/Tabs** - Organize workstreams into different pages
  - Drag-and-drop to reorder pages
  - Click pencil icon to rename pages
  - Switch between pages with tabs
- 📊 **Custom Workstream Swimlanes** - Organize JIRA tickets your way
- 🔍 **Flexible Queries** - Use JQL queries or specific ticket keys
- 🎨 **Color-coded Statuses** - Visual ticket status indicators
- 💾 **Server-side Persistence** - Workstreams saved to `workstreams.json`
- 🔄 **Smart Caching** - 1-hour cache for ticket details, automatic backups
- 📋 **Quick Navigation** - Jump between workstreams instantly

### View Modes

- 📊 **Cards View** - Kanban board with New/In Progress/Review/Done columns
- 📑 **Table View** - Sortable spreadsheet-style display with all columns
- 🌳 **Tree View** - Hierarchical visualization of epics, stories, subtasks, and
  dependencies
  - Auto-deduplication (each ticket appears once)
  - Collapsible nodes
  - Type icons (🚀 Epic, 📖 Story, 🐛 Bug, ✓ Task, 🔗 Link)
- 🏷️ **Grouping Options** - Group by Epic, Parent Link, or Assignee (Cards/Table
  view)

### Advanced Query Features

- 🔗 **Query Stacking** - Build complex queries by combining results
  - **FOREACH** - Iterate over query results with placeholders
    - `{issue}`, `{epic}`, `{parent}`, `{assignee}`, `{reporter}`
    - Example: `FOREACH {query1}: issuekey in childissuesof({issue})`
  - **Set Operations** - Combine queries with UNION, INTERSECT, SUBTRACT, XOR
    - Example: `{query1} UNION {query2}`
  - **Query References** - Use `{query1}`, `{query2}` in subsequent queries
  - Multiple queries execute sequentially and show individual results
- ⚠️ **Limit Warnings** - Visual warnings when queries hit JIRA's 100 ticket
  limit
  - Shows on workstream headers and individual query results
  - Tracks truncation in FOREACH iterations
  - Helps identify incomplete data

### Data & Export

- 📤 **Export/Import Configuration** - Share setups or backup your config
- 📊 **Export to CSV** - Download workstream data as spreadsheet
- 📝 **Markdown Export** - Export tickets with changelog for AI processing
  - Includes ticket details, descriptions, and recent changes
  - Filter by date range
- 🤖 **AI Summaries** (Experimental) - LLM-powered ticket change summaries
  - ⚠️ **Note**: This is an experimental feature that has not yet been verified
  - Supports OpenAI-compatible APIs
  - Filter by date range (7/14/30 days)
  - Custom context for tailored summaries
  - Omit inactive tickets option

### Display & Customization

- 📈 **Story Points** - Auto-detects and displays estimation fields
- 🏃 **Sprint Information** - Shows active/future sprint labels
- 🔀 **Reorderable** - Move workstreams up/down with arrows
- 🎯 **Status Tracking** - Shows completion percentage per workstream
- ⏱️ **Last Updated** - Timestamp showing data freshness

## Development

This app is completely vibe coded!

## Setup

### 0. Requirements

You must have [uv](https://docs.astral.sh/uv/) installed on your system.

### 1. Install Dependencies

```bash
uv sync
```

### 2. Get a JIRA API Token

**For Atlassian Cloud:**
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Give it a name (e.g., "pioj")
4. Copy the token (you won't be able to see it again!)

**For JIRA Server/Data Center:**
1. Go to your JIRA instance → Profile → Personal Access Tokens
2. Create a new token
3. Copy the token

### 3. Configure JIRA Credentials

Create a `.env` file in the project directory:

```bash
cp .env.example .env
```

Edit `.env` and fill in your details:

```bash
# For JIRA Server/Data Center
JIRA_HOST=https://jira.example.com
JIRA_EMAIL=
JIRA_TOKEN=your_personal_access_token

# For Atlassian Cloud
JIRA_HOST=https://yourcompany.atlassian.net
JIRA_EMAIL=your@email.com
JIRA_TOKEN=your_api_token
```

**Important:**

- `JIRA_EMAIL` should be empty for JIRA Server/Data Center
- `JIRA_EMAIL` is required for Atlassian Cloud
- `.env` file takes precedence over shell environment variables

**Optional Configuration:**

```bash
# Custom field names (if your JIRA uses non-standard names)
JIRA_ESTIMATION_FIELD=Story Points  # Default: auto-detects common names
JIRA_SPRINT_FIELD=Sprint           # Default: auto-detects sprint field

# AI Summary Integration (Optional)
LLM_API_KEY=your_api_key                        # Required for AI summaries
LLM_API_BASE=https://api.openai.com/v1         # Optional, defaults to OpenAI
LLM_MODEL=gpt-4o-mini                          # Optional, defaults to gpt-4o-mini
```

### 4. Run the Server

```bash
uv run server.py
```

The server will start on http://localhost:5000 and automatically load your
configuration from `.env`.

### 5. Open in Browser

Simply open http://localhost:5000 in your browser - no additional configuration
needed!

## Usage

### Organize with Pages

**Pages** allow you to organize workstreams into different tabs. Common use
cases:

- By sprint: "Sprint 42", "Sprint 43"
- By team: "Backend Team", "Frontend Team"
- By project: "Project Alpha", "Project Beta"

**To create a page:**

1. Click "+ New Page" in the tabs section
2. Give it a name
3. Switch to the page and add workstreams

**To manage pages:**

- **Rename**: Hover over tab and click the pencil icon (✎)
- **Reorder**: Drag and drop tabs to rearrange
- **Delete**: Hover over tab and click the "×" button (cannot delete last page)

### Add a Workstream

1. Make sure you're on the correct page/tab
2. Click "Add Workstream"
3. Give it a name (e.g., "Backend Team Sprint 23")
4. Add one or more queries

**Simple JQL Query:**

```
project = MYPROJ AND status != Done
assignee = currentUser() AND sprint in openSprints()
project = MYPROJ AND labels = backend
```

**Ticket Keys:**

```
PROJ-123, PROJ-456, PROJ-789
```

5. Click "Add" and then "Refresh" to load tickets

### Advanced Queries (Query Stacking)

Build complex queries by stacking and combining results. Each query can reference
previous queries.

**Query Types:**

1. **JQL** - Standard JIRA query
   - Can reference previous queries: `{query1}`, `{query2}`
   - Example: `key in ({query1})`

2. **FOREACH** - Iterate over results with placeholders
   - Placeholders: `{issue}`, `{epic}`, `{parent}`, `{assignee}`, `{reporter}`
   - Example: `FOREACH {query1}: issuekey in childissuesof({issue})`
   - Executes one query per result from previous query
   - Results are combined and deduplicated

3. **Set Operations** - Combine query results
   - `{query1} UNION {query2}` - All tickets from both queries
   - `{query1} INTERSECT {query2}` - Only tickets in both queries
   - `{query1} SUBTRACT {query2}` - Tickets in first but not second
   - `{query1} XOR {query2}` - Tickets in one or the other, but not both

**Example: Get all subtasks of epic's stories**

```
Query 1: issuekey = PROJ-123
Query 2 (FOREACH): FOREACH {query1}: issuekey in childissuesof({issue})
Query 3 (FOREACH): FOREACH {query2}: issuekey in childissuesof({issue})
```

**Example: Combine multiple projects**

```
Query 1: project = BACKEND AND sprint in openSprints()
Query 2: project = FRONTEND AND sprint in openSprints()
Query 3 (SET_OPERATION): {query1} UNION {query2}
```

**Understanding the 100 Ticket Limit:**

JIRA's API limits each query to 100 results. When a query hits this limit, you'll
see: **⚠️ 100 ticket limit reached**

This appears:
- In the workstream header (if ANY query was truncated)
- In individual query result headers (showing which specific query hit the limit)

### View Modes

Each workstream can be displayed in three different views:

**Cards View (Default)**

- Kanban-style cards organized by status columns (New/In Progress/Review/Done)
- Visual card-based layout with full details
- Shows ticket key, summary, status, assignee, and story points
- Sprint labels for active/future sprints
- More visual and easier to scan

**Table View**

- Spreadsheet-style table with all tickets in rows
- Columns: Key, Summary, Status, Sprint, Assignee, Story Points
- Sortable and compact display
- Better for viewing many tickets at once
- Shows all tickets regardless of status in a single scrollable table

**Tree View**

- Hierarchical tree structure showing ticket relationships
- Shows epics → stories → subtasks → linked issues
- Displays parent-child relationships
- Shows issue links (blocks, depends on, relates to)
- Collapsible/expandable nodes for exploring dependencies
- Icons indicate ticket types (🚀 Epic, 📖 Story, 🐛 Bug, ✓ Task, 🔗 Link)
- **Automatic de-duplication**: Each ticket appears only once in the tree (even
  if referenced multiple times)
- **Status badges**: Color-coded status displayed for all tickets in the
  hierarchy
- Perfect for understanding complex ticket dependencies and project structure
- **Note:** Grouping options are disabled in tree view as hierarchy is built-in

Toggle between views using the **Cards/Table/Tree** buttons in the workstream
config section.

### Manage Workstreams

- **Refresh**: Update tickets for a specific workstream (updates "Last updated"
  timestamp)
- **Refresh All**: Update all workstreams at once (with 1-second delay between
  refreshes to avoid rate limiting)
- **Cancel**: Stop a running refresh operation
- **Export CSV**: Download workstream tickets as a spreadsheet
- **Edit**: Modify the workstream name or queries
- **Delete**: Remove a workstream
- **Clear All Data**: Delete all workstreams on the current page

Each workstream displays:
- Ticket count and completion percentage
- "Last updated" timestamp (e.g., "5 minutes ago", "2 hours ago")
- Query result counts and execution times

### Export & Import Configuration

Share your workstream setup with teammates or back up your configuration.

**Export Configuration:**

1. Click "Export Config" in the controls bar
2. Downloads a JSON file with your pages and workstreams configuration
3. File includes: page names, workstream names, queries, grouping settings,
   view preferences
4. Does NOT include actual ticket data (that's fetched fresh from JIRA)

**Import Configuration:**

1. Click "Import Config" and select a JSON file
2. Choose import mode:
   - **Replace**: Removes all existing pages and replaces with imported config
   - **Merge**: Keeps existing pages and adds imported ones (with "(imported)"
     suffix)
3. Configuration is saved automatically
4. Click "Refresh All" to load ticket data from JIRA

**Use Cases:**

- Share your workstream setup with team members
- Backup your configuration before making changes
- Set up the same workstreams on multiple machines
- Migrate between different JIRA instances (just update the .env file)

### Export Workstream Data

**Export to CSV:**

1. Make sure the workstream has loaded tickets (click "Refresh" if needed)
2. Click "Export CSV" button on the workstream
3. Downloads a CSV file with all ticket data

**CSV Columns:** Key, Summary, Status, Assignee, Story Points, Type, Epic Key,
Epic Name, Parent Key, Parent Name

**Export to Markdown:**

1. Click "Export Markdown" on a workstream (requires tickets loaded)
2. Select date range for changelog (7/14/30 days)
3. Downloads markdown file with:
   - Ticket summaries and descriptions
   - Recent changes (filtered by date range)
   - Query definitions used
4. Perfect for AI processing, documentation, or reports

**Use Cases:**

- Share ticket lists with stakeholders who don't have JIRA access
- Create reports or presentations
- Analyze data in Excel/Google Sheets
- Process with AI tools
- Archive sprint data

### AI-Powered Summaries (Experimental)

⚠️ **Note**: This is an experimental feature that has not yet been thoroughly
verified. Use with caution and verify results.

Generate intelligent summaries of ticket changes using LLM integration.

**Setup:**

1. Configure in `.env`:
   ```bash
   LLM_API_KEY=your_api_key
   LLM_API_BASE=https://api.openai.com/v1  # Optional
   LLM_MODEL=gpt-4o-mini                   # Optional
   ```

2. Supports any OpenAI-compatible API (OpenAI, Azure OpenAI, local models, etc.)

**Usage:**

1. Load a workstream with tickets
2. Click "Generate AI Summary"
3. Select options:
   - **Date range**: Last 7/14/30 days
   - **Context**: Optional custom instructions
   - **Omit inactive**: Skip tickets with no changes/comments
4. View generated summary in the workstream

**Features:**

- Summarizes ticket changes and comments over time
- Uses cached data to minimize API calls
- Respects date range for focused summaries
- Custom context for tailored outputs

## Architecture

### Technology Stack

- **Backend**: Flask (Python)
  - Official `jira` Python library for JIRA API integration
  - Automatic Cloud (v3) vs Server/DC (v2) detection
  - Built-in connection pooling and session management
- **Frontend**: Vanilla JavaScript (no frameworks or build step)
- **Storage**: Server-side JSON file (`workstreams.json`)
- **Caching**: 1-hour cache for ticket details in `cache.json`

### Performance & Caching

**Smart Caching:**
- Ticket details (changelog + comments) cached for 1 hour
- Reduces JIRA API load significantly
- Filters cached data by date range on retrieval
- Automatic cache expiry

**Automatic Backups:**
- Creates backup before each save
- Keeps last 5 backups automatically
- Files: `workstreams_backup_*.json`

**Rate Limiting Protection:**
- 1-second delay between workstream refreshes
- Cancellable refresh operations
- Efficient query execution with result reuse

## Data Storage

Your workstream definitions are stored server-side in `workstreams.json` in the
project directory. This means:

- ✅ Workstreams persist across browser sessions
- ✅ Accessible from any browser
- ✅ Survives browser cache clearing
- ✅ Automatic backups (keeps last 5)
- ✅ Automatically migrates from localStorage on first load

The file is excluded from git via `.gitignore`, so your workstream
configurations remain local to your machine.

**Backup**: Export your config using "Export Config" or copy the
`workstreams.json` file.

## Security & Privacy

- Your JIRA credentials are only sent to the local Flask server (localhost:5000)
- No external services except JIRA API and optional LLM API
- Credentials stored in `.env` (gitignored)
- `workstreams.json` and `cache.json` are gitignored
- All data stays on your local machine

## Troubleshooting

**"Is the server running?" error**

- Make sure you ran `uv run server.py`
- Check that port 5000 is not being used by another application

**"Connection failed" error**

- Verify your JIRA host URL is correct (include https://)
- Double-check your email and API token
- Ensure you have access to the JIRA instance
- For Cloud: Email + API token required
- For Server/DC: Only token required (leave JIRA_EMAIL empty)

**"No tickets found"**

- Check your JQL query syntax
- Verify you have permission to view those tickets
- Try a simpler query first (e.g., just `project = MYPROJ`)

**"100 ticket limit reached" warning**

- Your query returned exactly 100 results (JIRA API limit)
- Results may be incomplete

**Environment variables not working**

- `.env` file now takes precedence over shell environment variables
- Restart the server after changing `.env`
- Check for typos in variable names

**AI Summary not working**

- Verify `LLM_API_KEY` is set in `.env`
- Check `LLM_API_BASE` if using custom endpoint
- Ensure workstream has tickets loaded

## Tips & Tricks

### Custom Fields

If your JIRA uses non-standard field names:

```bash
# In .env
JIRA_ESTIMATION_FIELD=Complexity Points
JIRA_SPRINT_FIELD=Custom Sprint Field
```

The app auto-detects common names:
- Estimation: "Story Points", "Points", "Estimate", "T-Shirt Size", "Effort", etc.
- Sprint: Standard sprint fields

### Query Performance

- Use specific JQL filters to reduce result sets
- Leverage caching - data is cached for 1 hour
- Cancel long-running queries if needed
- Use query stacking instead of complex JQL when possible

### Organizing Workstreams

- Create pages by sprint, team, or project
- Use descriptive workstream names
- Export config regularly as backup
- Group by Epic/Parent/Assignee for better organization

### Working with Large Datasets

- Split large queries into multiple smaller queries
- Use FOREACH to process results in batches
- Use set operations to combine filtered results
- Monitor the 100 ticket limit warnings

## Contributing

This project is vibe coded and not yet open for contributions. It's a personal
tool that may evolve over time based on individual needs.

## License

See LICENSE file for details.
