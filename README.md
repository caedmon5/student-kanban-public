# Student Reading Queue Automation

This repository contains scripts and workflows to manage a student reading queue on GitHub using private repos and a central Kanban board.

## Overview

- Each student has a private repository for submitting papers.
- Papers are submitted as GitHub issues using a standard template.
- Issues are automatically synced to a GitHub Project (v2) Kanban board.
- Status updates in the board are mirrored back to repo issues with labels and comments.
- A shared inbox repository can be used for students without GitHub accounts.

## Repository Structure

- students.csv — list of students (name, github_username).
- add_students.py — creates private repos for students, pushes issue templates, adds collaborators, and seeds an initial issue.
- paper-submission.md — issue template used for paper submissions.
- pull_issues_to_kanban.py — sync script that:
  - Adds issues from all student repos to the central Project.
  - Updates Status fields.
  - Posts comments when statuses change.
  - Mirrors board status into labels.
- update-kanban.yml — GitHub Actions workflow to run the sync on a schedule or manually.

## Setup

1) Prepare a GitHub token with repo and project permissions.
   In your repository: Settings > Secrets and variables > Actions > New repository secret
   Name the secret: GH_TOKEN

2) Create student repos
    python add_students.py

   This will:
   - Create a private repo for each student listed in students.csv.
   - Add the issue template.
   - Invite the student as a collaborator.
   - Open an initial placeholder issue.

3) Set up the inbox repo (optional)
   - Create a repo named reading-inbox.
   - Add .github/ISSUE_TEMPLATE/paper-submission.md to that repo (copy this file).
   - Ensure Issues are enabled in the repo settings.
   Use this repo to add papers for students without GitHub accounts.

4) Run the Kanban sync
   Trigger manually:
    python pull_issues_to_kanban.py
   Or let GitHub Actions run it via the update-kanban.yml workflow.

## Usage

- Students submit papers by creating issues in their repos with the provided template.
- You can add papers for non-GitHub students via the reading-inbox repo (same template).
- The Kanban board shows all submissions in one place.
- Status changes in the board trigger comments and labels in the original issue.

## Notes

- The workflow requires the correct permission key repository-projects (not projects) in update-kanban.yml.
- Ensure GH_TOKEN has access to both private repos and Projects (v2).

## License

This project is for instructional and academic use. Adapt as needed for your own lab or course.
