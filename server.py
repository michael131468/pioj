from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import json
from dotenv import load_dotenv
from jira import JIRA

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

def initialize_jira_client():
    """Initialize JIRA client with appropriate authentication"""
    if not jira_config['host'] or not jira_config['token']:
        return None

    try:
        if jira_config['email']:
            # Cloud: Basic Auth
            return JIRA(
                server=jira_config['host'],
                basic_auth=(jira_config['email'], jira_config['token'])
            )
        else:
            # Server/Data Center: Bearer token
            headers = JIRA.DEFAULT_OPTIONS["headers"].copy()
            headers["Authorization"] = f"Bearer {jira_config['token']}"
            return JIRA(
                server=jira_config['host'],
                options={"headers": headers}
            )
    except Exception as e:
        print(f"Failed to initialize JIRA client: {e}")
        return None

jira_client = initialize_jira_client()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/config/status', methods=['GET'])
def config_status():
    """Check if JIRA and LLM are configured"""
    is_configured = bool(jira_config['host'] and jira_config['token'])
    llm_configured = bool(llm_config['api_key'])

    # Test JIRA connection if configured
    jira_status = None
    auth_mode = None
    if is_configured:
        if jira_client:
            try:
                # Test connection using jira_client.myself()
                myself = jira_client.myself()
                jira_status = 'connected'
                auth_mode = 'Basic Auth (Cloud)' if jira_config['email'] else 'Bearer Token (Server/DC)'
            except Exception as e:
                jira_status = f'error: {str(e)}'
        else:
            jira_status = 'error: client initialization failed'

    return jsonify({
        'configured': is_configured,
        'host': jira_config['host'] if is_configured else None,
        'llm_configured': llm_configured,
        'jira_status': jira_status,
        'auth_mode': auth_mode
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

    if not jira_client:
        raise Exception('JIRA client not configured')

    # Use library to fetch issue with changelog
    issue = jira_client.issue(
        ticket_key,
        expand='changelog,renderedFields'
    )
    fields = issue.fields

    # Extract ticket details (handle None values)
    status = getattr(fields, 'status', None)
    assignee = getattr(fields, 'assignee', None)
    priority = getattr(fields, 'priority', None)

    ticket_details = {
        'key': ticket_key,
        'summary': getattr(fields, 'summary', 'No summary'),
        'status': status.name if status and hasattr(status, 'name') else 'Unknown',
        'assignee': assignee.displayName if assignee and hasattr(assignee, 'displayName') else 'Unassigned',
        'priority': priority.name if priority and hasattr(priority, 'name') else 'None',
        'description': getattr(fields, 'description', ''),
        'estimation': None,
        'sprint': None,
        'sprint_state': None,  # active, future, or closed
        'changes': [],  # Will store ALL changes with ISO dates
        'comments': []  # Will store ALL comments with ISO dates
    }

    # Try to find estimation field by name
    estimation_field_id = get_estimation_field_id()
    if estimation_field_id:
        estimation_value = getattr(fields, estimation_field_id, None)
        if estimation_value is not None:
            ticket_details['estimation'] = estimation_value

    # Try to find sprint field by name
    import re
    sprint_field_id = get_sprint_field_id()
    if sprint_field_id:
        sprint_data = getattr(fields, sprint_field_id, None)
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
    if hasattr(issue, 'changelog') and issue.changelog:
        histories = issue.changelog.histories if hasattr(issue.changelog, 'histories') else []
        for history in histories:
            created_str_raw = history.created if hasattr(history, 'created') else None
            if not created_str_raw:
                continue
            created = datetime.fromisoformat(str(created_str_raw).replace('Z', '+00:00'))
            author_obj = history.author if hasattr(history, 'author') else None
            author = author_obj.displayName if author_obj and hasattr(author_obj, 'displayName') else 'Unknown'
            created_str = created.strftime('%Y-%m-%d %H:%M')

            items = history.items if hasattr(history, 'items') else []
            for item in items:
                field = item.field if hasattr(item, 'field') else ''
                from_val = item.fromString if hasattr(item, 'fromString') else 'None'
                to_val = item.toString if hasattr(item, 'toString') else 'None'
                ticket_details['changes'].append({
                    'date': created_str,
                    'date_iso': created.isoformat(),  # Store ISO for filtering
                    'author': author,
                    'field': field,
                    'from': from_val if from_val else 'None',
                    'to': to_val if to_val else 'None'
                })

    # Extract ALL comments (no date filtering)
    comment_data = getattr(fields, 'comment', None)
    if comment_data:
        comments = comment_data.comments if hasattr(comment_data, 'comments') else []
        for comment in comments:
            created_str_raw = comment.created if hasattr(comment, 'created') else None
            if not created_str_raw:
                continue
            created = datetime.fromisoformat(str(created_str_raw).replace('Z', '+00:00'))
            author_obj = comment.author if hasattr(comment, 'author') else None
            author = author_obj.displayName if author_obj and hasattr(author_obj, 'displayName') else 'Unknown'
            created_str = created.strftime('%Y-%m-%d %H:%M')
            body = comment.body if hasattr(comment, 'body') else ''
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

    if not jira_client:
        return None

    # Return from cache if available
    if field_name in custom_field_cache:
        return custom_field_cache[field_name]

    # Fetch all fields from JIRA if cache is empty
    if not custom_field_cache:
        try:
            fields = jira_client.fields()
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
    if not jira_client:
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

        sprint_field = get_sprint_field_id()
        if sprint_field:
            fields.append(sprint_field)

        # Use library search
        issues = jira_client.search_issues(
            jql_str=jql,
            maxResults=100,
            fields=','.join(fields)
        )

        # Process results
        tickets = []
        epic_keys = set()
        parent_keys = set()

        for issue in issues:
            ticket = parse_issue(issue)
            tickets.append(ticket)
            if ticket.get('epicKey'):
                epic_keys.add(ticket['epicKey'])
            if ticket.get('parentKey'):
                parent_keys.add(ticket['parentKey'])

        # Fetch epic summaries using library
        epic_summaries = {}
        for epic_key in epic_keys:
            try:
                epic = jira_client.issue(epic_key, fields='summary')
                epic_summaries[epic_key] = epic.fields.summary if hasattr(epic.fields, 'summary') else epic_key
            except:
                epic_summaries[epic_key] = epic_key

        # Fetch parent summaries using library
        parent_summaries = {}
        for parent_key in parent_keys:
            # Skip if already fetched as epic
            if parent_key not in epic_summaries:
                try:
                    parent = jira_client.issue(parent_key, fields='summary')
                    parent_summaries[parent_key] = parent.fields.summary if hasattr(parent.fields, 'summary') else parent_key
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
                # Fetch with changelog expanded using library
                issue_with_changelog = jira_client.issue(
                    ticket['key'],
                    expand='changelog',
                    fields='status'
                )
                if hasattr(issue_with_changelog, 'changelog') and issue_with_changelog.changelog:
                    histories = issue_with_changelog.changelog.histories if hasattr(issue_with_changelog.changelog, 'histories') else []
                    # Look for most recent status change
                    for history in reversed(histories):
                        items = history.items if hasattr(history, 'items') else []
                        for item in items:
                            if hasattr(item, 'field') and item.field == 'status':
                                ticket['statusChangeDate'] = history.created if hasattr(history, 'created') else None
                                break
                        if ticket.get('statusChangeDate'):
                            break
            except:
                # If fetching changelog fails, just skip it
                pass

        return jsonify({'tickets': tickets})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/issue/<issue_key>', methods=['GET'])
def get_issue(issue_key):
    if not jira_client:
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

        sprint_field = get_sprint_field_id()
        if sprint_field:
            fields.append(sprint_field)

        # Use library to fetch issue
        issue = jira_client.issue(
            issue_key,
            fields=','.join(fields),
            expand='changelog'
        )

        return jsonify(parse_issue(issue))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def parse_issue(issue):
    """Parse JIRA library Issue object into dict format"""
    fields = issue.fields
    status = fields.status if hasattr(fields, 'status') else None
    assignee = fields.assignee if hasattr(fields, 'assignee') else None
    reporter = fields.reporter if hasattr(fields, 'reporter') else None
    priority = fields.priority if hasattr(fields, 'priority') else None
    issuetype = fields.issuetype if hasattr(fields, 'issuetype') else None

    # Get estimation value from custom field (Option 3: handle different types)
    story_points = None
    estimation_field = get_estimation_field_id()
    if estimation_field:
        estimation_value = getattr(fields, estimation_field, None)
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

    # Get sprint information
    sprint = None
    sprint_state = None
    sprint_field_id = get_sprint_field_id()
    if sprint_field_id:
        sprint_data = getattr(fields, sprint_field_id, None)
        if sprint_data:
            # Sprint data can be an array of sprint objects or strings
            if isinstance(sprint_data, list) and len(sprint_data) > 0:
                # Get the most recent sprint (last in array)
                last_sprint = sprint_data[-1]

                if isinstance(last_sprint, str):
                    # Parse sprint string format
                    import re
                    sprint_name_match = re.search(r'name=([^,\]]+)', last_sprint)
                    sprint_state_match = re.search(r'state=([^,\]]+)', last_sprint)

                    if sprint_name_match:
                        sprint = sprint_name_match.group(1)
                    if sprint_state_match:
                        sprint_state = sprint_state_match.group(1).lower()
                elif isinstance(last_sprint, dict):
                    # Sprint is already a dict object
                    sprint = last_sprint.get('name', 'Unknown Sprint')
                    sprint_state = (last_sprint.get('state') or '').lower()

    # Get parent and epic information
    parent_key = None
    parent_name = None
    epic_key = None
    epic_name = None

    # Try parent field first (standard field, used in JIRA Cloud native hierarchies and subtasks)
    parent = getattr(fields, 'parent', None)
    if parent:
        parent_key = parent.key if hasattr(parent, 'key') else None
        parent_name = parent.fields.summary if hasattr(parent, 'fields') and hasattr(parent.fields, 'summary') else parent_key

        # Check if parent is an Epic (JIRA Cloud native hierarchy)
        parent_issuetype = parent.fields.issuetype if hasattr(parent, 'fields') and hasattr(parent.fields, 'issuetype') else None
        parent_type_name = parent_issuetype.name if parent_issuetype and hasattr(parent_issuetype, 'name') else ''

        if parent_type_name.lower() == 'epic':
            # Parent is an Epic, so populate both epic and parent
            epic_key = parent_key
            epic_name = parent_name

    # Try Epic Link custom field (JIRA Server/Data Center, older JIRA Cloud)
    if not epic_key:
        epic_link_field = get_custom_field_id('Epic Link')
        if epic_link_field:
            epic_link = getattr(fields, epic_link_field, None)
            if epic_link:
                epic_key = epic_link
                epic_name = epic_link

    # Try Parent Link custom field (some JIRA instances use this for custom hierarchies)
    if not parent_key:
        parent_link_field = get_custom_field_id('Parent Link')
        if parent_link_field:
            parent_link = getattr(fields, parent_link_field, None)
            if parent_link:
                parent_key = parent_link
                parent_name = parent_link  # Will be fetched later

    # Get issue links (blocks, depends on, etc.)
    issue_links = []
    issuelinks = getattr(fields, 'issuelinks', []) or []
    for link in issuelinks:
        if hasattr(link, 'outwardIssue'):
            outward = link.outwardIssue
            issue_links.append({
                'type': link.type.outward if hasattr(link.type, 'outward') else '',
                'key': outward.key if hasattr(outward, 'key') else '',
                'summary': outward.fields.summary if hasattr(outward, 'fields') and hasattr(outward.fields, 'summary') else ''
            })
        if hasattr(link, 'inwardIssue'):
            inward = link.inwardIssue
            issue_links.append({
                'type': link.type.inward if hasattr(link.type, 'inward') else '',
                'key': inward.key if hasattr(inward, 'key') else '',
                'summary': inward.fields.summary if hasattr(inward, 'fields') and hasattr(inward.fields, 'summary') else ''
            })

    # Get subtasks
    subtasks = []
    subtasks_list = getattr(fields, 'subtasks', []) or []
    for subtask in subtasks_list:
        subtasks.append({
            'key': subtask.key if hasattr(subtask, 'key') else '',
            'summary': subtask.fields.summary if hasattr(subtask, 'fields') and hasattr(subtask.fields, 'summary') else '',
            'status': subtask.fields.status.name if hasattr(subtask, 'fields') and hasattr(subtask.fields, 'status') and hasattr(subtask.fields.status, 'name') else 'Unknown'
        })

    # Get resolution
    resolution = getattr(fields, 'resolution', None)
    resolution_name = resolution.name if resolution and hasattr(resolution, 'name') else None

    # Get status change date from changelog
    status_change_date = None
    if hasattr(issue, 'changelog') and issue.changelog:
        histories = issue.changelog.histories if hasattr(issue.changelog, 'histories') else []
        # Look for most recent status change
        for history in reversed(histories):
            items = history.items if hasattr(history, 'items') else []
            for item in items:
                if hasattr(item, 'field') and item.field == 'status':
                    status_change_date = history.created if hasattr(history, 'created') else None
                    break
            if status_change_date:
                break

    return {
        'key': issue.key,
        'summary': fields.summary if hasattr(fields, 'summary') else '',
        'status': status.name if status and hasattr(status, 'name') else 'Unknown',
        'statusCategory': status.statusCategory.key if status and hasattr(status, 'statusCategory') and hasattr(status.statusCategory, 'key') else 'other',
        'assignee': assignee.displayName if assignee and hasattr(assignee, 'displayName') else 'Unassigned',
        'reporter': reporter.displayName if reporter and hasattr(reporter, 'displayName') else 'Unknown',
        'priority': priority.name if priority and hasattr(priority, 'name') else 'None',
        'storyPoints': story_points,
        'type': issuetype.name if issuetype and hasattr(issuetype, 'name') else 'Task',
        'epicKey': epic_key,
        'epicName': epic_name,
        'parentKey': parent_key,
        'parentName': parent_name,
        'issueLinks': issue_links,
        'subtasks': subtasks,
        'resolution': resolution_name,
        'statusChangeDate': status_change_date,
        'sprint': sprint,
        'sprintState': sprint_state
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
                if not jira_client:
                    raise Exception('JIRA client not configured')

                # Use library to fetch issue with changelog
                issue = jira_client.issue(key, expand='changelog')
                fields = issue.fields

                # Ticket header
                summary = getattr(fields, 'summary', 'No summary')
                status = getattr(fields, 'status', None)
                assignee = getattr(fields, 'assignee', None)
                priority = getattr(fields, 'priority', None)

                markdown += f"### {key}: {summary}\n\n"
                markdown += f"- **Status:** {status.name if status and hasattr(status, 'name') else 'Unknown'}\n"
                markdown += f"- **Assignee:** {assignee.displayName if assignee and hasattr(assignee, 'displayName') else 'Unassigned'}\n"
                markdown += f"- **Priority:** {priority.name if priority and hasattr(priority, 'name') else 'None'}\n"

                # Add estimation if available
                estimation_field_id = get_estimation_field_id()
                if estimation_field_id:
                    estimation_value = getattr(fields, estimation_field_id, None)
                    if estimation_value:
                        markdown += f"- **Estimation:** {estimation_value}\n"

                markdown += f"- **URL:** {jira_config['host']}/browse/{key}\n\n"

                # Description
                description = getattr(fields, 'description', '')
                if description:
                    markdown += f"**Description:**\n{description[:500]}{'...' if len(description) > 500 else ''}\n\n"

                # Changelog
                recent_changes = []
                if hasattr(issue, 'changelog') and issue.changelog:
                    histories = issue.changelog.histories if hasattr(issue.changelog, 'histories') else []
                    for history in histories:
                        created_str_raw = history.created if hasattr(history, 'created') else None
                        if not created_str_raw:
                            continue
                        created = datetime.fromisoformat(str(created_str_raw).replace('Z', '+00:00'))
                        if created >= cutoff_date:
                            author_obj = history.author if hasattr(history, 'author') else None
                            author = author_obj.displayName if author_obj and hasattr(author_obj, 'displayName') else 'Unknown'
                            created_str = created.strftime('%Y-%m-%d %H:%M')

                            items = history.items if hasattr(history, 'items') else []
                            for item in items:
                                field = item.field if hasattr(item, 'field') else ''
                                from_val = item.fromString if hasattr(item, 'fromString') else 'None'
                                to_val = item.toString if hasattr(item, 'toString') else 'None'
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
        additional_context = data.get('context', '')
        omit_inactive = data.get('omit_inactive', False)

        if not ticket_keys:
            return jsonify({'error': 'No tickets provided'}), 400

        # Fetch changelog for all tickets (using cache)
        changelog_entries = []

        for key in ticket_keys:
            try:
                # Use cached ticket details
                ticket_details = get_cached_ticket_details(key, days)

                # Skip tickets with no activity if requested
                has_activity = (
                    len(ticket_details.get('changes', [])) > 0 or
                    len(ticket_details.get('comments', [])) > 0
                )

                if omit_inactive and not has_activity:
                    continue

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

                # Extract comment entries
                for comment in ticket_details.get('comments', []):
                    changelog_entries.append({
                        'ticket': key,
                        'date': comment['date'],
                        'author': comment['author'],
                        'field': 'comment',
                        'from': '',
                        'to': comment['body'][:100] + ('...' if len(comment['body']) > 100 else '')
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
        summary = call_llm(changelog_text, days, len(ticket_keys), len(changelog_entries), additional_context)

        return jsonify({
            'summary': summary,
            'changeCount': len(changelog_entries),
            'ticketCount': len(ticket_keys),
            'days': days
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def call_llm(changelog_text, days, ticket_count, change_count, additional_context=''):
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

        if additional_context:
            prompt += f"\n\nAdditional context/instructions: {additional_context}"

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
