import argparse
import csv
import json
import os
import subprocess
import shutil

# CONFIGURATION
GITHUB_ORG = None  # Set to your org name if you're using one; else None
VISIBILITY = "private"
BASE_REPO_PREFIX = "student-queue-"
TEMPLATE_DIR = "template"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if not GITHUB_ORG and not os.getenv("OWNER_LOGIN"):
    os.environ["OWNER_LOGIN"] = input("GitHub username (OWNER_LOGIN): ").strip()
if not os.getenv("INSTRUCTOR_NAME"):
    os.environ["INSTRUCTOR_NAME"] = input("Instructor name (e.g. Prof. O'Donnell): ").strip()
if not os.getenv("KANBAN_TOKEN"):
    val = input("KANBAN_TOKEN (PAT for dispatch, or Enter to skip): ").strip()
    if val:
        os.environ["KANBAN_TOKEN"] = val


def run(cmd):
    print(f"Running: {cmd}")
    try:
        subprocess.run(cmd, shell=True, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {cmd}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        raise

def create_repo(repo_name):
    org_flag = f"--org {GITHUB_ORG}" if GITHUB_ORG else ""
    run(f"gh repo create {org_flag} {repo_name} --{VISIBILITY} --")

def push_issue_template(repo_name):
    """Clone the student's repo, refresh template files, commit and push only
    if there are real changes. Empty (newly-created) repos get seeded with an
    initial main branch; existing repos get a normal non-force push so any
    student commits are preserved."""
    temp_dir = f"/tmp/{repo_name}"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    template_abs = os.path.join(SCRIPT_DIR, TEMPLATE_DIR)
    if not os.path.isdir(template_abs):
        raise FileNotFoundError(f"Expected template folder at {template_abs}, but it was not found.")

    account = GITHUB_ORG if GITHUB_ORG else os.getenv("OWNER_LOGIN")
    remote_url = f"https://github.com/{account}/{repo_name}.git"

    run(f"git clone {remote_url} {temp_dir}")
    os.chdir(temp_dir)

    # Empty repo (just created by gh repo create) has no commits or branches.
    head_check = subprocess.run(
        "git rev-parse --verify HEAD",
        shell=True, capture_output=True, text=True
    )
    is_empty_repo = head_check.returncode != 0

    # Replace each top-level template item wholesale: directories like .github/
    # are fully managed by the template (so removing a file from template/ also
    # removes it from student repos), while files outside template/ are untouched.
    for item in os.listdir(template_abs):
        src = os.path.join(template_abs, item)
        dst = os.path.join(temp_dir, item)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    instructor = os.getenv("INSTRUCTOR_NAME", "your instructor")
    for root, dirs, files in os.walk(temp_dir):
        if ".git" in dirs:
            dirs.remove(".git")
        for fname in files:
            if not fname.endswith(".md"):
                continue
            path = os.path.join(root, fname)
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            if "{INSTRUCTOR_NAME}" in text:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text.replace("{INSTRUCTOR_NAME}", instructor))

    run("git add -A")

    diff = subprocess.run("git diff --cached --quiet", shell=True)
    if diff.returncode == 0:
        print(f"⏭️  No template changes for {repo_name}; nothing to push.")
        os.chdir(SCRIPT_DIR)
        shutil.rmtree(temp_dir)
        return

    if is_empty_repo:
        run('git commit -m "Seed onboarding files"')
        run("git branch -M main")
        run("git push -u origin main")
    else:
        run('git commit -m "Update onboarding files"')
        run("git push origin HEAD")

    os.chdir(SCRIPT_DIR)
    shutil.rmtree(temp_dir)

def add_collaborator(repo_name, github_user):
    print(f"🔗 Adding collaborator {github_user} to {repo_name}")
    account = GITHUB_ORG if GITHUB_ORG else os.getenv("OWNER_LOGIN")
    repo_path = f"{account}/{repo_name}"
    # If the "student" is the owner, don't add as collaborator (GitHub forbids it)
    if github_user.strip().lower() == str(account).strip().lower():
        print(f"⏭️  {github_user} is the repository owner for {repo_path}; skipping collaborator step.")
        return
    run(
        f'gh api '
        f'--method PUT '
        f'/repos/{repo_path}/collaborators/{github_user} '
        f'-f permission=push'
    )

def create_initial_issue(repo_name, student_name):
    instructor = os.getenv("INSTRUCTOR_NAME", "your instructor")
    account = GITHUB_ORG if GITHUB_ORG else os.getenv("OWNER_LOGIN")
    repo_path = f"{account}/{repo_name}"

    # Ensure the submission label exists (also used by student-filed issues).
    try:
        run(f'gh label create submission --repo {repo_path} --color FF9A00 --description "Student paper submission"')
    except subprocess.CalledProcessError as e:
        if "already exists" in e.stderr:
            print(f"⚠️ Label 'submission' already exists in {repo_path}. Skipping label creation.")
        else:
            raise

    # Skip if a welcome issue already exists. Match both the current title and
    # the legacy one used by earlier runs of this script.
    new_title = "[Welcome] Read this first"
    legacy_title = "[Reading Request] Initial Placeholder"
    existing = subprocess.run(
        ["gh", "issue", "list", "--repo", repo_path, "--state", "all",
         "--limit", "200", "--json", "title"],
        capture_output=True, text=True, check=True
    )
    titles = {i["title"] for i in json.loads(existing.stdout or "[]")}
    if new_title in titles or legacy_title in titles:
        print(f"⏭️  Welcome issue already exists in {repo_path}; skipping creation.")
        return

    readme_url = f"https://github.com/{account}/{repo_name}/blob/main/README.md"
    body = f"""Hi {student_name},

Welcome to your private reading queue for {instructor}.

**Before you submit anything, read the [README]({readme_url})** in this repo. It explains how to file a submission, what each field is for, and what happens after you submit (status comments, labels, etc.).

Quick version:

- Click the **Issues** tab and choose **New issue** → **Paper Submission** for each paper.
- One paper per issue.
- The right-hand panel (Status, Priority, Activity Type) is managed by {instructor} via the Kanban board — you can't edit it. Use the **Priority** and **Deadline** fields in the issue body to communicate urgency instead.
- Don't edit or close this welcome issue; just leave it.

– {instructor}
"""
    run(f'gh issue create --repo {repo_path} --title "{new_title}" --body "{body}" --label "submission"')

def set_kanban_token(repo_name):
    """Push the KANBAN_TOKEN secret so the student repo can trigger kanban syncs."""
    account = GITHUB_ORG if GITHUB_ORG else os.getenv("OWNER_LOGIN")
    repo_path = f"{account}/{repo_name}"
    token = os.getenv("KANBAN_TOKEN")
    if not token:
        print("⚠️ KANBAN_TOKEN not set in environment; skipping secret setup.")
        return
    run(f'gh secret set KANBAN_TOKEN --repo {repo_path} --body "{token}"')

def main():
    parser = argparse.ArgumentParser(description="Provision / refresh student reading-queue repos.")
    parser.add_argument("--only", metavar="GITHUB_USERNAME",
                        help="Only process the student with this github_username (case-insensitive).")
    args = parser.parse_args()

    only = args.only.strip().lower() if args.only else None

    with open("students.csv") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            student_name = row["name"].strip()
            github_user = row["github_username"].strip()
            if only and github_user.lower() != only:
                continue
            repo_suffix = github_user.lower().replace(" ", "-")
            repo_name = BASE_REPO_PREFIX + repo_suffix

            print(f"\n📚 Processing {student_name} ({github_user})")

            # Step 1: Try to create the repo
            try:
                create_repo(repo_name)
            except subprocess.CalledProcessError as e:
                if e.stderr and "Name already exists" in e.stderr:
                    print(f"⚠️ Repo {repo_name} already exists. Skipping creation.")
                else:
                    raise

            # Step 2: Continue with the rest regardless
            push_issue_template(repo_name)
            add_collaborator(repo_name, github_user)
            create_initial_issue(repo_name, student_name)
            set_kanban_token(repo_name)

if __name__ == "__main__":
    main()
