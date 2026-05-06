# Your Reading Queue

This private repository is your personal channel for sending reading
requests, drafts, and questions to {INSTRUCTOR_NAME}. Everything you open
here as an "Issue" is automatically added to a shared Kanban board that
{INSTRUCTOR_NAME} uses to track what to read next.

You and {INSTRUCTOR_NAME} are the only people who can see this repo.

## How to submit a paper

1. Click the **Issues** tab at the top of this repository.
2. Click **New issue**.
3. Choose the **Paper Submission** template.
4. Fill in the body fields:
   - **Title** (the issue title at the top): replace `TITLE OF YOUR PAPER`
     with the actual title. Keep the `[Reading Request]` prefix — or use
     `[Read/Write Request]` for a draft of your own you want feedback on,
     or `[Question]` for something that isn't a submission.
   - **Paper title** — full title, plus author(s) and year if known.
   - **Link (URL)** — DOI, arXiv, journal URL, or a Drive / Dropbox link.
     Paywalled and you don't have a public copy? Paste the DOI and add a
     short note about where to find it.
   - **Action required** — what you want done (read, review, comments on
     a draft, sign-off, FYI, etc.).
   - **Deadline or suggested date** — an ISO date if you have one, or a
     phrase like "no rush". Leave blank if it's genuinely open-ended.
   - **Priority** — tick one of the three options.
   - **Any questions or comments** — anything else worth knowing.
5. Click **Submit new issue**.

One paper per issue, please.

## Ignore the right-hand panel

When you view an issue, GitHub shows a panel on the right with **Status**,
**Priority**, **Activity Type**, etc. **You can't edit those, and you
don't need to** — they belong to {INSTRUCTOR_NAME}'s Kanban board, which
spans every student's queue and isn't shared with you. Communicate
urgency through the **Priority** and **Deadline** fields in the issue
body instead, and {INSTRUCTOR_NAME} will mirror them onto the board.

## What happens after you submit

- Your issue is automatically added to {INSTRUCTOR_NAME}'s Kanban board.
- As {INSTRUCTOR_NAME} moves the card across the board, you will see:
  - a **comment** on your issue announcing the status change (with an
    `@`-mention, so you also get a GitHub notification), and
  - a **label** such as `status: Reading` on the issue, replacing the
    previous one.
- Status names come from {INSTRUCTOR_NAME}'s board (typically things like
  "Queued", "In Progress", "Returned to Student", "Done"). The comment
  text always names the change explicitly, so you don't need to memorise
  the column names.

## Things to avoid

- **Don't edit the welcome issue** that was opened for you when this repo
  was created. It's a pointer to this README, not a submission slot. Open
  a new issue for each paper.
- **Don't close issues yourself.** {INSTRUCTOR_NAME} closes them when the
  paper has been read or discussed.
- **Don't add or remove `status:` labels by hand.** They're managed by
  the sync script and any manual changes will be overwritten.

## Questions?

Open an issue here and start the title with `[Question]` instead of
`[Reading Request]`, or email {INSTRUCTOR_NAME} directly.
