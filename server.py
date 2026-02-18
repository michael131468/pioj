from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import base64
import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# Path to store workstreams data
WORKSTREAMS_FILE = 'workstreams.json'
CACHE_FILE = 'cache.json'
CACHE_EXPIRY_HOURS = 1

# Load JIRA config from environment variables
jira_config = {
    'host': os.getenv('JIRA_HOST', '').rstrip('/'),
    'email': os.getenv('JIRA_EMAIL', ''),
    'token': os.getenv('JIRA_TOKEN', ''),
    'estimation_field': os.getenv('JIRA_ESTIMATION_FIELD', ''),
    'sprint_field': os.getenv('JIRA_SPRINT_FIELD', '')
}

# Load LLM config from environment variables (optional - for summaries)
llm_config = {
    'api_key': os.getenv('LLM_API_KEY', ''),
    'api_base': os.getenv('LLM_API_BASE', None),  # None = OpenAI default
    'model': os.getenv('LLM_MODEL', 'gpt-4o-mini')
}

# Cache for custom field mappings (name -> field ID)
custom_field_cache = {}

# Validate configuration on startup
if not jira_config['host'] or not jira_config['token']:
    print('\n' + '='*60)
    print('WARNING: JIRA configuration incomplete!')
    print('Please create a .env file with JIRA_HOST and JIRA_TOKEN')
    print('See .env.example for reference')
    print('='*60 + '\n')

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/config/status', methods=['GET'])
def config_status():
    """Check if JIRA is configured"""
    is_configured = bool(jira_config['host'] and jira_config['token'])
    return jsonify({
        'configured': is_configured,
        'host': jira_config['host'] if is_configured else None
    })

@app.route('/api/workstreams', methods=['GET'])
def get_workstreams():
    """Load workstreams from file"""
    try:
        if os.path.exists(WORKSTREAMS_FILE):
            with open(WORKSTREAMS_FILE, 'r') as f:
                workstreams = json.load(f)
            return jsonify({'workstreams': workstreams})
        else:
            return jsonify({'workstreams': []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/workstreams', methods=['POST'])
def save_workstreams():
    """Save workstreams to file with backup"""
    try:
        data_to_save = request.json

        # Create backup if file exists and has content
        if os.path.exists(WORKSTREAMS_FILE):
            with open(WORKSTREAMS_FILE, 'r') as f:
                existing = f.read()
                if existing and existing != '[]' and existing != '{}':
                    import time
                    backup_file = f'workstreams_backup_{int(time.time())}.json'
                    with open(backup_file, 'w') as bf:
                        bf.write(existing)

                    # Keep only last 5 backups
                    backups = sorted([f for f in os.listdir('.') if f.startswith('workstreams_backup_')])
                    for old_backup in backups[:-5]:
                        os.remove(old_backup)

        # Save new data
        with open(WORKSTREAMS_FILE, 'w') as f:
            json.dump(data_to_save, f, indent=2)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_auth_headers():
    """Get authentication headers based on config"""
    if jira_config['email']:
        # Cloud: Use Basic Auth with email + token
        auth_str = f"{jira_config['email']}:{jira_config['token']}"
        encoded = base64.b64encode(auth_str.encode()).decode()
        return {'Authorization': f'Basic {encoded}'}
    else:
        # Server/Data Center: Use Bearer token
        return {'Authorization': f'Bearer {jira_config["token"]}'}

def load_cache():
    """Load cache from cache.json"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading cache: {e}")
    return {}

def save_cache(cache):
    """Save cache to cache.json"""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Error saving cache: {e}")

def is_cache_fresh(cached_data, hours=CACHE_EXPIRY_HOURS):
    """Check if cached data is fresh (less than specified hours old)"""
    if not cached_data or 'cached_at' not in cached_data:
        return False

    from datetime import datetime, timezone, timedelta
    cached_at = datetime.fromisoformat(cached_data['cached_at'])
    now = datetime.now(timezone.utc)
    age = now - cached_at

    return age < timedelta(hours=hours)

def filter_ticket_data_by_date(full_data, days):
    """Filter changelog and comments by date range"""
    from datetime import datetime, timedelta, timezone
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    filtered_data = full_data.copy()
    filtered_data['changes'] = []
    filtered_data['comments'] = []

    # Filter changes
    for change in full_data.get('changes', []):
        change_date = datetime.fromisoformat(change['date_iso'])
        if change_date >= cutoff_date:
            filtered_data['changes'].append({
                'date': change['date'],
                'date_iso': change['date_iso'],
                'author': change['author'],
                'field': change['field'],
                'from': change['from'],
                'to': change['to']
            })

    # Filter comments
    for comment in full_data.get('comments', []):
        comment_date = datetime.fromisoformat(comment['date_iso'])
        if comment_date >= cutoff_date:
            filtered_data['comments'].append({
                'date': comment['date'],
                'date_iso': comment['date_iso'],
                'author': comment['author'],
                'body': comment['body']
            })

    return filtered_data

def get_cached_ticket_details(ticket_key, days):
    """Get ticket details from cache or fetch from JIRA if stale/missing"""
    cache = load_cache()
    cache_key = ticket_key  # No days suffix - cache full data

    # Check if we have fresh cached data
    if cache_key in cache and is_cache_fresh(cache[cache_key]):
        print(f"Cache hit for {ticket_key}")
        # Filter cached data by requested time range
        filtered_data = filter_ticket_data_by_date(cache[cache_key]['data'], days)
        filtered_data['_cache_hit'] = True
        return filtered_data

    # Fetch from JIRA
    print(f"Cache miss for {ticket_key}, fetching from JIRA")
    from datetime import datetime, timedelta, timezone

    response = requests.get(
        f"{jira_config['host']}/rest/api/2/issue/{ticket_key}",
        headers=get_auth_headers(),
        params={'expand': 'changelog,renderedFields'},
        timeout=10
    )

    if not response.ok:
        raise Exception(f'Failed to fetch {ticket_key}: HTTP {response.status_code}')

    issue = response.json()
    fields = issue.get('fields', {})

    # Extract ticket details (handle None values with 'or {}')
    ticket_details = {
        'key': ticket_key,
        'summary': fields.get('summary', 'No summary'),
        'status': (fields.get('status') or {}).get('name', 'Unknown'),
        'assignee': (fields.get('assignee') or {}).get('displayName', 'Unassigned'),
        'priority': (fields.get('priority') or {}).get('name', 'None'),
        'description': fields.get('description', ''),
        'estimation': None,
        'sprint': None,
        'sprint_state': None,  # active, future, or closed
        'changes': [],  # Will store ALL changes with ISO dates
        'comments': []  # Will store ALL comments with ISO dates
    }

    # Try to find estimation field by name
    estimation_field_id = get_estimation_field_id()
    if estimation_field_id and estimation_field_id in fields:
        ticket_details['estimation'] = fields[estimation_field_id]

    # Try to find sprint field by name
    import re
    sprint_field_id = get_sprint_field_id()
    if sprint_field_id:
        sprint_data = fields.get(sprint_field_id)
        if sprint_data:
            # Sprint data can be an array of sprint objects or strings
            if isinstance(sprint_data, list) and len(sprint_data) > 0:
                # Get the most recent sprint (last in array)
                last_sprint = sprint_data[-1]

                if isinstance(last_sprint, str):
                    # Parse sprint string format: "com.atlassian.greenhopper.service.sprint.Sprint@14b1c359[id=123,rapidViewId=456,state=ACTIVE,name=Sprint 1,...]"
                    sprint_name_match = re.search(r'name=([^,\]]+)', last_sprint)
                    sprint_state_match = re.search(r'state=([^,\]]+)', last_sprint)

                    if sprint_name_match:
                        ticket_details['sprint'] = sprint_name_match.group(1)
                    if sprint_state_match:
                        ticket_details['sprint_state'] = sprint_state_match.group(1).lower()
                elif isinstance(last_sprint, dict):
                    # Sprint is already a dict object
                    ticket_details['sprint'] = last_sprint.get('name', 'Unknown Sprint')
                    ticket_details['sprint_state'] = (last_sprint.get('state') or '').lower()

    # Extract ALL changelog (no date filtering)
    changelog = issue.get('changelog') or {}
    for history in (changelog.get('histories') or []):
        created = datetime.fromisoformat(history['created'].replace('Z', '+00:00'))
        author = (history.get('author') or {}).get('displayName', 'Unknown')
        created_str = created.strftime('%Y-%m-%d %H:%M')

        for item in (history.get('items') or []):
            field = item.get('field', '')
            from_val = item.get('fromString', 'None')
            to_val = item.get('toString', 'None')
            ticket_details['changes'].append({
                'date': created_str,
                'date_iso': created.isoformat(),  # Store ISO for filtering
                'author': author,
                'field': field,
                'from': from_val,
                'to': to_val
            })

    # Extract ALL comments (no date filtering)
    comment_data = fields.get('comment') or {}
    comments = comment_data.get('comments') or []
    for comment in comments:
        created = datetime.fromisoformat(comment['created'].replace('Z', '+00:00'))
        author = (comment.get('author') or {}).get('displayName', 'Unknown')
        created_str = created.strftime('%Y-%m-%d %H:%M')
        body = comment.get('body', '')
        ticket_details['comments'].append({
            'date': created_str,
            'date_iso': created.isoformat(),  # Store ISO for filtering
            'author': author,
            'body': body
        })

    # Cache the FULL result (all changes and comments)
    cache[cache_key] = {
        'cached_at': datetime.now(timezone.utc).isoformat(),
        'data': ticket_details
    }
    save_cache(cache)

    # Return filtered data for the requested time range
    filtered_data = filter_ticket_data_by_date(ticket_details, days)
    filtered_data['_cache_hit'] = False
    return filtered_data

def get_custom_field_id(field_name):
    """Get custom field ID by name, with caching"""
    global custom_field_cache

    # Return from cache if available
    if field_name in custom_field_cache:
        return custom_field_cache[field_name]

    # Fetch all fields from JIRA if cache is empty
    if not custom_field_cache:
        try:
            response = requests.get(
                f"{jira_config['host']}/rest/api/2/field",
                headers=get_auth_headers(),
                timeout=10
            )
            if response.ok:
                fields = response.json()
                # Build cache mapping from field names to field IDs
                for field in fields:
                    if field.get('custom'):
                        name = field.get('name', '').lower()
                        field_id = field.get('id')
                        if name and field_id:
                            custom_field_cache[name] = field_id
        except Exception as e:
            print(f"Warning: Could not fetch custom fields: {e}")

    # Return field ID if found, otherwise None
    return custom_field_cache.get(field_name.lower())

def get_estimation_field_id():
    """Get estimation field ID, trying env var override first, then common names"""
    # Option 2: Try environment variable override first
    if jira_config.get('estimation_field'):
        field_id = get_custom_field_id(jira_config['estimation_field'])
        if field_id:
            return field_id

    # Option 1: Try common estimation field names
    common_names = [
        'Story point estimate',  # Atlassian default
        'Story Points',
        'Points',
        'Estimate',
        'Story points',
        'Effort',
        'T-Shirt Size',
        'Size'
    ]

    for field_name in common_names:
        field_id = get_custom_field_id(field_name)
        if field_id:
            return field_id

    return None

def get_sprint_field_id():
    """Get sprint field ID, trying env var override first, then common names"""
    # Try environment variable override first
    if jira_config.get('sprint_field'):
        field_id = get_custom_field_id(jira_config['sprint_field'])
        if field_id:
            return field_id

    # Try common sprint field names
    common_names = [
        'Sprint',
        'Sprints',
        'Active Sprint',
        'Active Sprints'
    ]

    for field_name in common_names:
        field_id = get_custom_field_id(field_name)
        if field_id:
            return field_id

    return None

@app.route('/api/search', methods=['POST'])
def search_issues():
    if not jira_config['host']:
        return jsonify({'error': 'JIRA not configured'}), 400

    data = request.json
    jql = data.get('jql')

    if not jql:
        return jsonify({'error': 'JQL query required'}), 400

    try:
        # Build fields list with dynamic custom field IDs
        fields = ['summary', 'status', 'assignee', 'reporter', 'priority', 'issuetype', 'parent', 'issuelinks', 'subtasks', 'resolution']

        # Add custom fields if found
        estimation_field = get_estimation_field_id()
        if estimation_field:
            fields.append(estimation_field)

        epic_link_field = get_custom_field_id('Epic Link')
        if epic_link_field:
            fields.append(epic_link_field)

        parent_link_field = get_custom_field_id('Parent Link')
        if parent_link_field:
            fields.append(parent_link_field)

        response = requests.post(
            f"{jira_config['host']}/rest/api/2/search",
            headers=get_auth_headers(),
            json={
                'jql': jql,
                'maxResults': 100,
                'fields': fields
            },
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        tickets = []
        epic_keys = set()
        parent_keys = set()

        for issue in result.get('issues', []):
            ticket = parse_issue(issue)
            tickets.append(ticket)
            if ticket.get('epicKey'):
                epic_keys.add(ticket['epicKey'])
            if ticket.get('parentKey'):
                parent_keys.add(ticket['parentKey'])

        # Fetch epic summaries
        epic_summaries = {}
        for epic_key in epic_keys:
            try:
                epic_response = requests.get(
                    f"{jira_config['host']}/rest/api/2/issue/{epic_key}",
                    headers=get_auth_headers(),
                    params={'fields': 'summary'},
                    timeout=10
                )
                if epic_response.ok:
                    epic_data = epic_response.json()
                    epic_summaries[epic_key] = epic_data.get('fields', {}).get('summary', epic_key)
            except:
                epic_summaries[epic_key] = epic_key

        # Fetch parent summaries
        parent_summaries = {}
        for parent_key in parent_keys:
            # Skip if already fetched as epic
            if parent_key not in epic_summaries:
                try:
                    parent_response = requests.get(
                        f"{jira_config['host']}/rest/api/2/issue/{parent_key}",
                        headers=get_auth_headers(),
                        params={'fields': 'summary'},
                        timeout=10
                    )
                    if parent_response.ok:
                        parent_data = parent_response.json()
                        parent_summaries[parent_key] = parent_data.get('fields', {}).get('summary', parent_key)
                except:
                    parent_summaries[parent_key] = parent_key
            else:
                parent_summaries[parent_key] = epic_summaries[parent_key]

        # Update tickets with epic and parent summaries
        for ticket in tickets:
            if ticket.get('epicKey') and ticket['epicKey'] in epic_summaries:
                ticket['epicName'] = epic_summaries[ticket['epicKey']]
            if ticket.get('parentKey') and ticket['parentKey'] in parent_summaries:
                ticket['parentName'] = parent_summaries[ticket['parentKey']]

        # Fetch status change dates for in-progress and review tickets
        in_progress_tickets = [
            t for t in tickets
            if t.get('statusCategory') in ['indeterminate'] or
               (t.get('status', '').lower().find('review') != -1)
        ]

        for ticket in in_progress_tickets:
            try:
                changelog_response = requests.get(
                    f"{jira_config['host']}/rest/api/2/issue/{ticket['key']}",
                    headers=get_auth_headers(),
                    params={'expand': 'changelog', 'fields': 'status'},
                    timeout=10
                )
                if changelog_response.ok:
                    issue_data = changelog_response.json()
                    changelog = issue_data.get('changelog', {})
                    if changelog:
                        histories = changelog.get('histories', [])
                        # Look for most recent status change
                        for history in reversed(histories):
                            for item in history.get('items', []):
                                if item.get('field') == 'status':
                                    ticket['statusChangeDate'] = history.get('created')
                                    break
                            if ticket.get('statusChangeDate'):
                                break
            except:
                # If fetching changelog fails, just skip it
                pass

        return jsonify({'tickets': tickets})
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/issue/<issue_key>', methods=['GET'])
def get_issue(issue_key):
    if not jira_config['host']:
        return jsonify({'error': 'JIRA not configured'}), 400

    try:
        # Build fields list with dynamic custom field IDs
        fields = ['summary', 'status', 'assignee', 'reporter', 'priority', 'issuetype', 'parent', 'issuelinks', 'subtasks', 'resolution']

        # Add custom fields if found
        estimation_field = get_estimation_field_id()
        if estimation_field:
            fields.append(estimation_field)

        epic_link_field = get_custom_field_id('Epic Link')
        if epic_link_field:
            fields.append(epic_link_field)

        parent_link_field = get_custom_field_id('Parent Link')
        if parent_link_field:
            fields.append(parent_link_field)

        response = requests.get(
            f"{jira_config['host']}/rest/api/2/issue/{issue_key}",
            headers=get_auth_headers(),
            params={
                'fields': ','.join(fields),
                'expand': 'changelog'
            },
            timeout=10
        )
        response.raise_for_status()
        issue = response.json()

        return jsonify(parse_issue(issue))
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

def parse_issue(issue):
    fields = issue.get('fields', {})
    status = fields.get('status', {}) or {}
    assignee = fields.get('assignee') or {}
    reporter = fields.get('reporter') or {}
    priority = fields.get('priority') or {}
    issuetype = fields.get('issuetype', {}) or {}

    # Get estimation value from custom field (Option 3: handle different types)
    story_points = None
    estimation_field = get_estimation_field_id()
    if estimation_field:
        estimation_value = fields.get(estimation_field)
        if estimation_value is not None:
            # Handle numeric values (story points, hours, etc.)
            if isinstance(estimation_value, (int, float)):
                # Convert to int if it's a whole number
                if isinstance(estimation_value, float) and estimation_value.is_integer():
                    story_points = int(estimation_value)
                else:
                    story_points = estimation_value
            # Handle string values (t-shirt sizes, etc.)
            elif isinstance(estimation_value, str):
                story_points = estimation_value
            # Handle object values (some fields return {value: "M", id: "123"})
            elif isinstance(estimation_value, dict):
                story_points = estimation_value.get('value') or estimation_value.get('name')
            # For other types, convert to string
            else:
                story_points = str(estimation_value)

    # Get parent and epic information
    parent_key = None
    parent_name = None
    epic_key = None
    epic_name = None

    # Try parent field first (standard field, used in JIRA Cloud native hierarchies and subtasks)
    parent = fields.get('parent')
    if parent:
        parent_key = parent.get('key')
        parent_name = parent.get('fields', {}).get('summary', parent_key)

        # Check if parent is an Epic (JIRA Cloud native hierarchy)
        parent_issuetype = parent.get('fields', {}).get('issuetype', {}) or {}
        parent_type_name = parent_issuetype.get('name', '')

        if parent_type_name.lower() == 'epic':
            # Parent is an Epic, so populate both epic and parent
            epic_key = parent_key
            epic_name = parent_name

    # Try Epic Link custom field (JIRA Server/Data Center, older JIRA Cloud)
    if not epic_key:
        epic_link_field = get_custom_field_id('Epic Link')
        if epic_link_field:
            epic_link = fields.get(epic_link_field)
            if epic_link:
                epic_key = epic_link
                epic_name = epic_link

    # Try Parent Link custom field (some JIRA instances use this for custom hierarchies)
    if not parent_key:
        parent_link_field = get_custom_field_id('Parent Link')
        if parent_link_field:
            parent_link = fields.get(parent_link_field)
            if parent_link:
                parent_key = parent_link
                parent_name = parent_link  # Will be fetched later

    # Get issue links (blocks, depends on, etc.)
    issue_links = []
    for link in fields.get('issuelinks', []):
        link_type = link.get('type', {}).get('name', '')
        if 'outwardIssue' in link:
            issue_links.append({
                'type': link.get('type', {}).get('outward', ''),
                'key': link['outwardIssue'].get('key'),
                'summary': link['outwardIssue'].get('fields', {}).get('summary', '')
            })
        if 'inwardIssue' in link:
            issue_links.append({
                'type': link.get('type', {}).get('inward', ''),
                'key': link['inwardIssue'].get('key'),
                'summary': link['inwardIssue'].get('fields', {}).get('summary', '')
            })

    # Get subtasks
    subtasks = []
    for subtask in fields.get('subtasks', []):
        subtasks.append({
            'key': subtask.get('key'),
            'summary': subtask.get('fields', {}).get('summary', ''),
            'status': subtask.get('fields', {}).get('status', {}).get('name', 'Unknown')
        })

    # Get resolution
    resolution = fields.get('resolution')
    resolution_name = resolution.get('name') if resolution else None

    # Get status change date from changelog
    status_change_date = None
    changelog = issue.get('changelog', {})
    if changelog:
        histories = changelog.get('histories', [])
        # Look for most recent status change
        for history in reversed(histories):
            for item in history.get('items', []):
                if item.get('field') == 'status':
                    status_change_date = history.get('created')
                    break
            if status_change_date:
                break

    return {
        'key': issue.get('key'),
        'summary': fields.get('summary', ''),
        'status': status.get('name', 'Unknown'),
        'statusCategory': status.get('statusCategory', {}).get('key', 'other'),
        'assignee': assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned',
        'reporter': reporter.get('displayName', 'Unknown') if reporter else 'Unknown',
        'priority': priority.get('name', 'None') if priority else 'None',
        'storyPoints': story_points,
        'type': issuetype.get('name', 'Task'),
        'epicKey': epic_key,
        'epicName': epic_name,
        'parentKey': parent_key,
        'parentName': parent_name,
        'issueLinks': issue_links,
        'subtasks': subtasks,
        'resolution': resolution_name,
        'statusChangeDate': status_change_date
    }

@app.route('/api/ticket/details', methods=['POST'])
def get_ticket_details():
    """Get detailed ticket information including changelog (with caching)"""
    if not jira_config['host']:
        return jsonify({'error': 'JIRA not configured'}), 400

    try:
        data = request.json
        ticket_key = data.get('key', '')
        days = data.get('days', 7)

        if not ticket_key:
            return jsonify({'error': 'No ticket key provided'}), 400

        # Use cached data if available and fresh
        ticket_details = get_cached_ticket_details(ticket_key, days)
        return jsonify(ticket_details)

    except Exception as e:
        print(f"Error fetching ticket details: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/workstream/export', methods=['POST'])
def export_workstream_markdown():
    """Export workstream tickets and changelogs as markdown"""
    if not jira_config['host']:
        return jsonify({'error': 'JIRA not configured'}), 400

    try:
        data = request.json
        ticket_keys = data.get('tickets', [])
        days = data.get('days', 7)
        workstream_name = data.get('name', 'Workstream')
        queries = data.get('queries', [])

        if not ticket_keys:
            return jsonify({'error': 'No tickets provided'}), 400

        from datetime import datetime, timedelta, timezone
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Build markdown content
        markdown = f"# {workstream_name}\n\n"
        markdown += f"**Export Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        markdown += f"**Time Range:** Last {days} days\n"
        markdown += f"**Ticket Count:** {len(ticket_keys)}\n\n"

        # Add queries if provided
        if queries:
            markdown += "## Queries\n\n"
            for i, query in enumerate(queries, 1):
                query_name = query.get('name', f'Query {i}')
                query_jql = query.get('jql', '')
                markdown += f"{i}. **{query_name}**\n   ```jql\n   {query_jql}\n   ```\n\n"

        markdown += "## Tickets\n\n"

        # Fetch full details for each ticket
        for key in ticket_keys:
            try:
                response = requests.get(
                    f"{jira_config['host']}/rest/api/2/issue/{key}",
                    headers=get_auth_headers(),
                    params={'expand': 'changelog'},
                    timeout=10
                )

                if response.ok:
                    issue = response.json()
                    fields = issue.get('fields', {})

                    # Ticket header
                    markdown += f"### {key}: {fields.get('summary', 'No summary')}\n\n"
                    markdown += f"- **Status:** {fields.get('status', {}).get('name', 'Unknown')}\n"
                    markdown += f"- **Assignee:** {fields.get('assignee', {}).get('displayName', 'Unassigned')}\n"
                    markdown += f"- **Priority:** {fields.get('priority', {}).get('name', 'None')}\n"

                    # Add estimation if available
                    for field_name in ['Story Points', 'Story point estimate', 'customfield_10016', 'customfield_10026']:
                        if field_name in fields and fields[field_name]:
                            markdown += f"- **Estimation:** {fields[field_name]}\n"
                            break

                    markdown += f"- **URL:** {jira_config['host']}/browse/{key}\n\n"

                    # Description
                    description = fields.get('description', '')
                    if description:
                        markdown += f"**Description:**\n{description[:500]}{'...' if len(description) > 500 else ''}\n\n"

                    # Changelog
                    changelog = issue.get('changelog', {})
                    recent_changes = []

                    for history in changelog.get('histories', []):
                        created = datetime.fromisoformat(history['created'].replace('Z', '+00:00'))
                        if created >= cutoff_date:
                            author = history.get('author', {}).get('displayName', 'Unknown')
                            created_str = created.strftime('%Y-%m-%d %H:%M')

                            for item in history.get('items', []):
                                field = item.get('field', '')
                                from_val = item.get('fromString', 'None')
                                to_val = item.get('toString', 'None')
                                recent_changes.append(f"- `{created_str}` **{author}**: {field} changed from `{from_val}` to `{to_val}`")

                    if recent_changes:
                        markdown += f"**Recent Changes (Last {days} days):**\n"
                        markdown += "\n".join(recent_changes) + "\n\n"
                    else:
                        markdown += f"*No changes in the last {days} days*\n\n"

                    markdown += "---\n\n"

            except Exception as e:
                print(f"Error fetching {key}: {e}")
                markdown += f"### {key}\n*Error fetching details*\n\n---\n\n"
                continue

        return jsonify({'markdown': markdown})

    except Exception as e:
        print(f"Error generating markdown: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/workstream/summary', methods=['POST'])
def generate_workstream_summary():
    """Generate an LLM summary of ticket changes in a workstream"""
    if not jira_config['host']:
        return jsonify({'error': 'JIRA not configured'}), 400

    if not llm_config['api_key']:
        return jsonify({'error': 'LLM not configured. Set LLM_API_KEY in .env file'}), 400

    try:
        data = request.json
        ticket_keys = data.get('tickets', [])
        days = data.get('days', 7)

        if not ticket_keys:
            return jsonify({'error': 'No tickets provided'}), 400

        # Fetch changelog for all tickets (using cache)
        changelog_entries = []

        for key in ticket_keys:
            try:
                # Use cached ticket details
                ticket_details = get_cached_ticket_details(key, days)

                # Extract changelog entries
                for change in ticket_details.get('changes', []):
                    changelog_entries.append({
                        'ticket': key,
                        'date': change['date'],
                        'author': change['author'],
                        'field': change['field'],
                        'from': change['from'],
                        'to': change['to']
                    })
            except Exception as e:
                print(f"Error fetching changelog for {key}: {e}")
                continue

        if not changelog_entries:
            return jsonify({
                'summary': f"No changes found in the last {days} days.",
                'changeCount': 0
            })

        # Format changelog for LLM
        changelog_text = "\n".join([
            f"[{entry['date']}] {entry['ticket']} - {entry['author']}: {entry['field']} changed from '{entry['from']}' to '{entry['to']}'"
            for entry in changelog_entries
        ])

        # Call LLM to generate summary
        summary = call_llm(changelog_text, days, len(ticket_keys), len(changelog_entries))

        return jsonify({
            'summary': summary,
            'changeCount': len(changelog_entries),
            'ticketCount': len(ticket_keys),
            'days': days
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def call_llm(changelog_text, days, ticket_count, change_count):
    """Call OpenAI-compatible LLM API to generate summary"""
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=llm_config['api_key'],
            base_url=llm_config['api_base']
        )

        prompt = f"""Analyze these JIRA ticket changes from the last {days} days ({change_count} changes across {ticket_count} tickets) and provide a concise, actionable summary.

Changes:
{changelog_text}

Please provide a brief summary focusing on:
1. Major progress and completions
2. Active work areas
3. Any blockers or concerning patterns
4. Notable status changes
5. Key trends

Keep it concise (3-5 bullet points) and actionable for a team standup."""

        response = client.chat.completions.create(
            model=llm_config['model'],
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=1024,
            temperature=0.7
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        raise Exception(f"LLM API error: {str(e)}")

if __name__ == '__main__':
    print('=' * 60)
    print('pioj')
    print('=' * 60)

    if jira_config['host'] and jira_config['token']:
        print(f'JIRA Host: {jira_config["host"]}')
        if jira_config['email']:
            print(f'Auth Mode: Cloud (email: {jira_config["email"]})')
        else:
            print('Auth Mode: Server/Data Center (Bearer token)')
        print('✓ Configuration loaded from .env')
    else:
        print('⚠ JIRA not configured - create .env file')

    print('=' * 60)
    print('Server running at: http://localhost:5000')
    print('Open http://localhost:5000 in your browser')
    print('Press Ctrl+C to stop')
    print('=' * 60)
    app.run(debug=True, port=5000)
