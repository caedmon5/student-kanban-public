"""
One-off script to push the notify-kanban workflow and KANBAN_TOKEN secret
to all existing student-queue-* repos.

Usage:
    export KANBAN_TOKEN="ghp_your_pat_here"
    python update_existing_repos.py
"""

import csv
import os
import shutil
import subprocess

GITHUB_USER = os.getenv("OWNER_LOGIN")
if not GITHUB_USER:
    GITHUB_USER = input("GitHub username (OWNER_LOGIN): ").strip()
    os.environ["OWNER_LOGIN"] = GITHUB_USER
if not os.getenv("KANBAN_TOKEN"):
    val = input("KANBAN_TOKEN (PAT for dispatch, or Enter to skip): ").strip()
    if val:
        os.environ["KANBAN_TOKEN"] = val
CSV_PATH = "students.csv"
BASE_REPO_PREFIX = "student-queue-"
WORKFLOW_SRC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "template", ".github", "workflows", "notify-kanban.yml",
)


def run(cmd):
    print(f"Running: {cmd}")
    try:
        subprocess.run(cmd, shell=True, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {cmd}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        raise


def push_workflow(repo_name):
    """Clone the repo, add the workflow file, push."""
    repo_path = f"{GITHUB_USER}/{repo_name}"
    temp_dir = f"/tmp/{repo_name}"

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    run(f"gh repo clone {repo_path} {temp_dir}")

    dest_dir = os.path.join(temp_dir, ".github", "workflows")
    os.makedirs(dest_dir, exist_ok=True)
    shutil.copy2(WORKFLOW_SRC, dest_dir)

    os.chdir(temp_dir)
    run("git add .github/workflows/notify-kanban.yml")

    # Check if there's actually anything to commit
    result = subprocess.run(
        "git diff --cached --quiet", shell=True, capture_output=True
    )
    if result.returncode == 0:
        print(f"⏩ {repo_name}: workflow already present, nothing to commit.")
    else:
        run('git commit -m "Add kanban notification workflow"')
        run("git push")
        print(f"✅ {repo_name}: workflow pushed.")

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    shutil.rmtree(temp_dir)


def set_secret(repo_name):
    """Set the KANBAN_TOKEN secret on the repo."""
    token = os.getenv("KANBAN_TOKEN")
    if not token:
        print("⚠️ KANBAN_TOKEN not set in environment; skipping secret.")
        return
    repo_path = f"{GITHUB_USER}/{repo_name}"
    run(f'gh secret set KANBAN_TOKEN --repo {repo_path} --body "{token}"')
    print(f"🔑 {repo_name}: KANBAN_TOKEN secret set.")


def main():
    if not os.path.isfile(WORKFLOW_SRC):
        raise FileNotFoundError(f"Workflow template not found at {WORKFLOW_SRC}")

    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            github_user = row.get("github_username", "").strip()
            if not github_user:
                continue
            repo_suffix = github_user.lower().replace(" ", "-")
            repo_name = BASE_REPO_PREFIX + repo_suffix

            print(f"\n📦 Updating {repo_name}...")
            try:
                push_workflow(repo_name)
                set_secret(repo_name)
            except Exception as e:
                print(f"⚠️ Failed to update {repo_name}: {e}")


if __name__ == "__main__":
    main()
