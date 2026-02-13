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

# Load JIRA config from environment variables
jira_config = {
    'host': os.getenv('JIRA_HOST', '').rstrip('/'),
    'email': os.getenv('JIRA_EMAIL', ''),
    'token': os.getenv('JIRA_TOKEN', ''),
    'estimation_field': os.getenv('JIRA_ESTIMATION_FIELD', '')
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
        fields = ['summary', 'status', 'assignee', 'priority', 'issuetype', 'parent', 'issuelinks', 'subtasks', 'resolution']

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
        fields = ['summary', 'status', 'assignee', 'priority', 'issuetype', 'parent', 'issuelinks', 'subtasks', 'resolution']

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
