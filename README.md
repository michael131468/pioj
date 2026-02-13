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
5. You want to keep your magic JIRA understanding to yourself and not share it.

## Development

This app is completely vibe coded!

## Features

- 📄 **Multiple Pages/Tabs** - Organize workstreams into different pages (e.g.,
  by sprint, team, or project)
- 📊 Organize JIRA tickets into custom workstream swimlanes
- 🔍 Use JQL queries or specific ticket keys to define each workstream
- 🎨 Color-coded ticket statuses (To Do, In Progress, Done)
- 💾 Server-side persistence - workstreams saved to `workstreams.json`
- 📤 **Export/Import configuration** - Share setups with teammates or backup
  your config
- 📊 **Export to CSV** - Export workstream ticket data to spreadsheet format
- 🔄 Refresh individual swimlanes or all at once
- 📋 Quick navigation to jump between workstreams
- 🔀 Reorder workstreams with up/down arrows
- 🏷️ Group tickets by Epic or Parent Link
- 📊 Kanban board view with New/In Progress/Review/Done columns
- 👁️ **Multiple view modes** - Cards (kanban), Table (spreadsheet), or Tree
  (hierarchical)
- 🌳 **Tree view** - Visualize ticket hierarchies, dependencies, and
  relationships
- 📈 Story points display on tickets

## Setup

### 0. Requirements

You must have [uv](https://docs.astral.sh/uv/) installed on your system.

### 1. Install Dependencies

```bash
uv install
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

**Optional Configuration:**

- `JIRA_ESTIMATION_FIELD` - Custom field name for estimation (default: auto-detects "Story Points", "Points", "Estimate", "T-Shirt Size", etc.)
  - Use this if your JIRA uses a non-standard name like "Complexity" or "Effort Points"
  - Example: `JIRA_ESTIMATION_FIELD=T-Shirt Size`

**Reminder**

If you have these environment variables set in your shell, they will override
what you set in the .env file.

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

**To delete a page:**

- Hover over the tab and click the "×" button
- Note: You cannot delete the last page

### Add a Workstream

1. Make sure you're on the correct page/tab
2. Click "Add Workstream"
3. Give it a name (e.g., "Backend Team Sprint 23")
4. Enter a JQL query or comma-separated ticket keys

**JQL Examples:**

```
project = MYPROJ AND status != Done
assignee = currentUser() AND sprint in openSprints()
project = MYPROJ AND labels = backend
```

**Ticket Keys Example:**

```
PROJ-123, PROJ-456, PROJ-789
```

4. Click "Add" and then "Refresh" to load tickets

### Manage Workstreams

- **Refresh**: Update tickets for a specific workstream (updates "Last updated"
  timestamp)
- **Refresh All**: Update all workstreams at once
- **Export CSV**: Download workstream tickets as a spreadsheet
- **Edit**: Modify the workstream name or query
- **Delete**: Remove a workstream
- **Clear All Data**: Delete all workstreams on the current page

Each workstream displays a "Last updated" timestamp at the bottom showing when
the data was last refreshed (e.g., "5 minutes ago", "2 hours ago", or the full
date for older refreshes).

### View Modes

Each workstream can be displayed in three different views:

**Cards View (Default)**

- Kanban-style cards organized by status columns (New/In Progress/Review/Done)
- Visual card-based layout with full details
- Shows ticket key, summary, status, assignee, and story points
- More visual and easier to scan

**Table View**

- Spreadsheet-style table with all tickets in rows
- Columns: Key, Summary, Status, Assignee, Story Points
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

### Export & Import Configuration

Share your workstream setup with teammates or back up your configuration.

**Export Configuration:**

1. Click "Export Config" in the controls bar
2. Downloads a JSON file with your pages and workstreams configuration
3. File includes: page names, workstream names, JQL queries, grouping settings,
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

### Export Workstream Data to Spreadsheet

Export ticket data from any workstream to a CSV file that can be opened in
Excel, Google Sheets, or any spreadsheet application.

**How to Export:**

1. Make sure the workstream has loaded tickets (click "Refresh" if needed)
2. Click "Export CSV" button on the workstream you want to export
3. Downloads a CSV file with all ticket data

**CSV Columns:**

- Key - JIRA ticket key
- Summary - Ticket description
- Status - Current status
- Assignee - Who it's assigned to
- Story Points - Estimation points
- Type - Issue type (Task, Bug, Story, etc.)
- Epic Key - Associated epic key
- Epic Name - Epic summary
- Parent Key - Parent issue key
- Parent Name - Parent issue summary

**Filename Format:** `workstream_name-TIMESTAMP.csv`

**Use Cases:**

- Share ticket lists with stakeholders who don't have JIRA access
- Create reports or presentations
- Analyze data in Excel/Google Sheets
- Archive sprint data
- Import into other tools

## Notes

- Your JIRA credentials are only sent to the local Flask server (localhost)
- Workstream definitions are saved in your browser's localStorage
- The server keeps your credentials in memory while running
- Click on any ticket key to open it in JIRA

## Troubleshooting

**"Is the server running?" error**

- Make sure you ran `python server.py`
- Check that port 5000 is not being used by another application

**"Connection failed" error**

- Verify your JIRA host URL is correct (include https://)
- Double-check your email and API token
- Ensure you have access to the JIRA instance

**"No tickets found"**

- Check your JQL query syntax
- Verify you have permission to view those tickets
- Try a simpler query first (e.g., just `project = MYPROJ`)

## Data Storage

Your workstream definitions are stored server-side in `workstreams.json` in the
project directory. This means:

- ✅ Workstreams persist across browser sessions
- ✅ Accessible from any browser
- ✅ Survives browser cache clearing
- ✅ Automatically migrates from localStorage on first load

The file is excluded from git via `.gitignore`, so your workstream
configurations remain local to your machine.

**Backup**: To backup your workstreams, simply copy the `workstreams.json` file.
