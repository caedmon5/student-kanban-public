# pull_issues_to_kanban.py (GraphQL version for GitHub Projects Beta)
# Requires: GH_TOKEN with project write access
# Assumes: Student issues already exist in private repos
# Adds them to a GitHub Projects (Beta) board under a given field (e.g., "Status")

import os
import requests
import csv
import datetime
import time
import re

token = os.getenv("GH_TOKEN")
if not token:
    raise EnvironmentError("GH_TOKEN not found in environment")


# --- CONFIGURATION ---
GITHUB_USER = os.getenv("OWNER_LOGIN")
if not GITHUB_USER:
    raise EnvironmentError("OWNER_LOGIN must be set (your GitHub username or org).")
PROJECT_TITLE = f"@{GITHUB_USER}'s Student Reading Queue"  # Exact name of the beta project
FIELD_NAME = "Status"            # Field in the project for columns (e.g., "Status")
# FIELD_VALUE = "Received"            # The value to set (e.g., move to "To do")
CSV_PATH = "students.csv"        # Path to the student CSV list
PROJECT_NUMBER = os.getenv("PROJECT_NUMBER")
OWNER_LOGIN = os.getenv("OWNER_LOGIN", GITHUB_USER)

GITHUB_API_URL = "https://api.github.com/graphql"
TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json"
}

REST_HEADERS = HEADERS  # same token, different endpoints
REST_ROOT = "https://api.github.com"

if not TOKEN:
    raise EnvironmentError("GH_TOKEN or GITHUB_TOKEN must be set.")

# Also scan these manual repositories (for students without GitHub)
ADDITIONAL_REPOS = [r.strip() for r in os.getenv("ADDITIONAL_REPOS", "").split(",") if r.strip()]


# --- GraphQL helpers ---
def graphql(query, variables=None):
    response = requests.post(GITHUB_API_URL, json={"query": query, "variables": variables}, headers=HEADERS)
    if not response.ok:
        # Fail with full body so we see why (rate limit, auth, etc.)
        raise requests.HTTPError(f"GraphQL HTTP {response.status_code}: {response.text}")
    payload = response.json()
    # If GitHub returns an errors[] block, surface it directly (avoids KeyError: 'data')
    if "errors" in payload and not payload.get("data"):
        first = payload["errors"][0]
        raise RuntimeError(f"GraphQL error: {first.get('message')} (path={first.get('path')})")
    return payload

# --- Comment change-detection helpers ---
MARKER = "<!-- kanban-status-bot -->"

def get_status_comment(owner, repo, issue_number):
    """Return (comment_id, status_text) for the bot comment if present, else (None, None)."""
    url = f"{REST_ROOT}/repos/{owner}/{repo}/issues/{issue_number}/comments"
    r = requests.get(url, headers=REST_HEADERS)
    r.raise_for_status()
    for c in r.json():
        body = c.get("body", "")
        if body.startswith(MARKER):
            m = re.search(r"^Status:\s*\*\*(.+?)\*\*", body, re.MULTILINE)
            return c["id"], (m.group(1).strip() if m else None)
    return None, None

# 1. Get GitHub username from CSV row for mention
#mention = github_username  # already in our CSV row
#body = (
#    f"@{mention} — Status changed from **{last_status or 'None'}** to **{current_status}** "
#    f"(_{datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_)"
#)
#url = f"{REST_ROOT}/repos/{GITHUB_USER}/{repo_name}/issues/{issue['number']}/comments"
#r = requests.post(url, headers=REST_HEADERS, json={"body": body})
#r.raise_for_status()

# --- Label mirroring helpers ---
def ensure_label_exists(owner, repo, name, color="6E9EFF", description="Mirrored board status"):
    url = f"{REST_ROOT}/repos/{owner}/{repo}/labels"
    # Try create; 422 means it already exists
    r = requests.post(url, headers=REST_HEADERS, json={"name": name, "color": color, "description": description})
    if r.status_code not in (200,201,422):
        r.raise_for_status()

def list_issue_labels(owner, repo, issue_number):
    url = f"{REST_ROOT}/repos/{owner}/{repo}/issues/{issue_number}/labels"
    r = requests.get(url, headers=REST_HEADERS)
    r.raise_for_status()
    return [lbl["name"] for lbl in r.json()]

def remove_issue_label(owner, repo, issue_number, name):
    # DELETE /issues/{number}/labels/{name}
    url = f"{REST_ROOT}/repos/{owner}/{repo}/issues/{issue_number}/labels/{requests.utils.quote(name, safe='')}"
    r = requests.delete(url, headers=REST_HEADERS)
    if r.status_code not in (200,204,404):  # 404 = already gone
        r.raise_for_status()

def add_issue_label(owner, repo, issue_number, name):
    url = f"{REST_ROOT}/repos/{owner}/{repo}/issues/{issue_number}/labels"
    r = requests.post(url, headers=REST_HEADERS, json={"labels": [name]})
    r.raise_for_status()

# --- Project item lookup + status read ---
def find_project_item_for_issue(project_id, issue_node_id):
    query = """
    query($projectId: ID!, $first: Int!, $after: String) {
      node(id: $projectId) {
        ... on ProjectV2 {
          items(first: $first, after: $after) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              content { __typename ... on Issue { id number repository { name } } }
              fieldValues(first: 50) {
                nodes {
                  __typename
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    field { ... on ProjectV2SingleSelectField { name } }
                    name
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    after = None
    while True:
        data = graphql(query, {"projectId": project_id, "first": 50, "after": after})
        items = data["data"]["node"]["items"]["nodes"]
        for it in items:
            c = it.get("content")
            if c and c.get("__typename") == "Issue" and c["id"] == issue_node_id:
                return it
        pi = data["data"]["node"]["items"]["pageInfo"]
        if not pi["hasNextPage"]:
            return None
        after = pi["endCursor"]

def extract_status_from_item(project_item_node):
    if not project_item_node:
        return None
    for fv in project_item_node["fieldValues"]["nodes"]:
        if fv["__typename"] == "ProjectV2ItemFieldSingleSelectValue":
            fld = fv.get("field")
            if fld and fld.get("name") == FIELD_NAME:
                return fv.get("name")
    return None


# --- Step 1: Get project ID ---
def get_project_id():
    """
    Resolve the ProjectV2 ID.
    Priority:
      1) PROJECT_NUMBER + OWNER_LOGIN (stable, rename-proof)
      2) Legacy: exact title match under GITHUB_USER
    """
    if PROJECT_NUMBER:
        try:
            number = int(PROJECT_NUMBER)
        except ValueError:
            raise ValueError(f"PROJECT_NUMBER must be an integer, got: {PROJECT_NUMBER!r}")

        q_user = """
        query($login: String!, $number: Int!) {
          user(login: $login) { projectV2(number: $number) { id title number } }
        }"""
        data_user = graphql(q_user, {"login": OWNER_LOGIN, "number": number})
        proj_user = ((data_user.get("data") or {}).get("user") or {}).get("projectV2")
        if proj_user and proj_user.get("id"):
            print(f"Selected project by number (user): {OWNER_LOGIN}/projects/{number} → '{proj_user.get('title')}'")
            return proj_user["id"]

        q_org = """
        query($login: String!, $number: Int!) {
          organization(login: $login) { projectV2(number: $number) { id title number } }
        }"""
        data_org = graphql(q_org, {"login": OWNER_LOGIN, "number": number})
        proj_org = ((data_org.get("data") or {}).get("organization") or {}).get("projectV2")
        if proj_org and proj_org.get("id"):
            print(f"Selected project by number (org): {OWNER_LOGIN}/projects/{number} → '{proj_org.get('title')}'")
            return proj_org["id"]

        raise ValueError(f"PROJECT_NUMBER={number} not found for owner '{OWNER_LOGIN}'")

    # Fallback: exact title (legacy)
    query = """
    query($login: String!) {
      user(login: $login) {
        projectsV2(first: 20) { nodes { id title } }
      }
    }"""
    data = graphql(query, {"login": GITHUB_USER})
    try:
        projects = data["data"]["user"]["projectsV2"]["nodes"]
    except KeyError:
        print("❌ Unexpected response from GitHub:", data)
        raise RuntimeError("Could not extract project list — check token and GITHUB_USER/OWNER_LOGIN.")

    for project in projects:
        if project["title"] == PROJECT_TITLE:
            print(f"Selected project by title: {project['title']}")
            return project["id"]

    print("Available project titles:")
    for project in projects:
        print(f"- {project['title']}")
    raise ValueError("Project not found. Set PROJECT_NUMBER or correct PROJECT_TITLE.")

# --- Step 2: Get field ID and value ID ---
def get_field_and_value_id(project_id):
    query = """
    query($projectId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          fields(first: 20) {
            nodes {
              ... on ProjectV2Field {
                id
                name
              }
              ... on ProjectV2SingleSelectField {
                id
                name
                options {
                  id
                  name
                }
              }
            }
          }
        }
      }
    }
    """
    data = graphql(query, {"projectId": project_id})

    print("Fields returned from GraphQL:")
    import pprint; pprint.pprint(data)


    for field in data["data"]["node"]["fields"]["nodes"]:
        if field.get("name") == FIELD_NAME:
            # Handle select fields with options
            if "options" in field:
                for option in field["options"]:
                    if option["name"] == FIELD_VALUE:
                        return field["id"], option["id"]
            else:
                return field["id"], None
    raise ValueError("Field or value not found")

# --- Step 3: Add an issue to the project ---
def add_issue_to_project(project_id, issue_id):
    mutation = """
    mutation($projectId:ID!, $contentId:ID!) {
      addProjectV2ItemById(input:{projectId:$projectId, contentId:$contentId}) {
        item {
          id
        }
      }
    }
    """
    response = graphql(mutation, {"projectId": project_id, "contentId": issue_id})
    print(f"✅ GitHub responded with: {response}")


# --- Step 4: Get issues from student repos ---
def get_issues_for_repo(repo_name):
    query = """
    query($owner: String!, $name: String!, $after: String) {
      repository(owner: $owner, name: $name) {
        issues(first: 100, states: [OPEN, CLOSED], orderBy: {field: CREATED_AT, direction: ASC}, after: $after) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            number
            title
            state
          }
        }
      }
    }
    """
    all_issues = []
    after = None
    while True:
        resp = graphql(query, {"owner": GITHUB_USER, "name": repo_name, "after": after})
        try:
            issues_data = resp["data"]["repository"]["issues"]
        except KeyError:
            raise RuntimeError(f"Bad GraphQL response for {repo_name}: {resp}")
        all_issues.extend(issues_data["nodes"])
        if not issues_data["pageInfo"]["hasNextPage"]:
            break
        after = issues_data["pageInfo"]["endCursor"]
    return all_issues

# --- MAIN SCRIPT ---
def main():
    print(f"🔁 Script run at {datetime.datetime.now().isoformat()}")

    project_id = get_project_id()
#    field_id, value_id = get_field_and_value_id(project_id)
    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)
        print("CSV Headers:", reader.fieldnames)  # DEBUG: print header fields
        for row in reader:
            github_username = row.get('github_username', '').strip()
            if not github_username:
                print(f"⚠️ Skipping row with missing github_username: {row}")
                continue
            # Normalise to match repo naming used elsewhere (lowercase, hyphenated)
            repo_suffix = github_username.lower().replace(" ", "-")
            repo_name = f"student-queue-{repo_suffix}"
            try:
                issues = get_issues_for_repo(repo_name)
                for issue in issues:
                    print(f"📌 Adding issue #{issue['number']} from {repo_name} to project")
                    add_issue_to_project(project_id, issue["id"])
                    # Read current Status from the project item
                    item = find_project_item_for_issue(project_id, issue["id"])
                    current_status = extract_status_from_item(item) or "No Status"

                    # Detect changes using the existing status: label as memory
                    labels = list_issue_labels(GITHUB_USER, repo_name, issue["number"])
                    prev_label = next((lbl for lbl in labels if lbl.lower().startswith("status:")), None)
                    prev_status = prev_label.split(":", 1)[1].strip() if prev_label else None

                    if prev_status != current_status:
                        print(f"🔔 {repo_name}#{issue['number']}: {prev_status!r} → {current_status!r}")

                        # 1) Post a new comment to trigger notification
                        mention = github_username
                        body = (
                            f"@{mention} — Status changed from **{prev_status or 'None'}** to **{current_status}** "
                            f"(_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_)"
                        )
                        url = f"{REST_ROOT}/repos/{GITHUB_USER}/{repo_name}/issues/{issue['number']}/comments"
                        r = requests.post(url, headers=REST_HEADERS, json={"body": body})
                        r.raise_for_status()

                        # 2) Replace any existing status:* label with the new one
                        if prev_label:
                            remove_issue_label(GITHUB_USER, repo_name, issue["number"], prev_label)
                        new_label = f"status: {current_status}"
                        ensure_label_exists(GITHUB_USER, repo_name, new_label)
                        add_issue_label(GITHUB_USER, repo_name, issue["number"], new_label)
                    else:
                        print(f"⏩ {repo_name}#{issue['number']}: status unchanged ({current_status})")



                    time.sleep(0.5)  # Avoid hitting rate limits
            except Exception as e:
                print(f"⚠️ Failed to process {repo_name}: {e}")

    # Also process manual inbox repos (for non-GitHub students)
    for repo_name in ADDITIONAL_REPOS:
        try:
            issues = get_issues_for_repo(repo_name)
            for issue in issues:
                print(f"📌 Adding issue #{issue['number']} from {repo_name} to project")
                add_issue_to_project(project_id, issue["id"])

                # Read current Status from the project item
                item = find_project_item_for_issue(project_id, issue["id"])
                current_status = extract_status_from_item(item) or "No Status"

                # Detect changes using the existing status: label as memory
                labels = list_issue_labels(GITHUB_USER, repo_name, issue["number"])
                prev_label = next((lbl for lbl in labels if lbl.lower().startswith("status:")), None)
                prev_status = prev_label.split(":", 1)[1].strip() if prev_label else None

                if prev_status != current_status:
                    print(f"🔔 {repo_name}#{issue['number']}: {prev_status!r} → {current_status!r}")

                    # Post a comment (no @mention, as student may not have a GH account)
                    body = (
                        f"Status changed from **{prev_status or 'None'}** to **{current_status}** "
                        f"(_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_)"
                    )
                    url = f"{REST_ROOT}/repos/{GITHUB_USER}/{repo_name}/issues/{issue['number']}/comments"
                    r = requests.post(url, headers=REST_HEADERS, json={"body": body})
                    r.raise_for_status()

                    # Replace any existing status:* label with the new one
                    if prev_label:
                        remove_issue_label(GITHUB_USER, repo_name, issue["number"], prev_label)
                    new_label = f"status: {current_status}"
                    ensure_label_exists(GITHUB_USER, repo_name, new_label)
                    add_issue_label(GITHUB_USER, repo_name, issue["number"], new_label)
                else:
                    print(f"⏩ {repo_name}#{issue['number']}: status unchanged ({current_status})")

                time.sleep(0.5)
        except Exception as e:
            print(f"⚠️ Failed to process {repo_name}: {e}")


if __name__ == "__main__":
    main()
