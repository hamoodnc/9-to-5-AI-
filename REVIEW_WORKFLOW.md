# Versioned application review

The existing FastAPI, service modules, SQLite database, and dashboard are retained.
Gemini generation and its retry/backoff wrapper are unchanged. No automatic submission
has been added. Mark Applied remains a manual tracking action.

## Run locally

Stop any existing development server before restarting it so no old worker can use
unversioned approval logic. From PowerShell:

```powershell
Set-Location 'C:\9-5 AI'
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/dashboard and refresh the browser to load the updated UI.
Existing local integration configuration is used normally; this change does not alter .env.
This remains the existing single-user local application; user authentication is not added.

## Database migration

On startup, an additive, transactional migration adds content_version, approved_version,
approved_at, history event/version fields, and an application_versions table. Existing
application content and history remain. Existing content receives version 1; empty drafts
remain at version 0. Legacy approvals are invalidated because they were not tied to a
content version. Previously recorded tracking outcomes are retained as historical state,
but cannot authorize new transitions without approval. Migration is safe to run again.

## Review workflow

1. Generate content. The saved version is ready_for_review with no approval.
2. Read or edit both text fields. Unsaved edits disable approval and Mark Applied.
3. Save changes. Changed text creates a new immutable snapshot and increments the version.
4. Click Approve current version and confirm the displayed saved version.
5. The card shows Approved - version N. Only now can Mark Applied be used.
6. Editing either field after approval clears approval on save and returns to review.
7. Needs Changes keeps the application ready_for_review and allows edits or regeneration.
8. View History shows generation, edits, approvals, invalidation, and tracking events.

Saving identical text does not create a new version or revoke approval. Regeneration
always creates a new version requiring review, even if its text happens to be identical.
Changing content after a manually recorded application also requires new approval;
its previous tracking events remain in history.

A stale save or approval returns HTTP 409. The dashboard keeps unsaved text on screen.
Copy any conflicting edits you want to retain, refresh applications, review the latest
version, and reapply your edits. Refreshing warns before discarding unsaved changes.

Correct Status cannot manufacture approval. Moving to review invalidates approval;
marking applied or recording downstream outcomes requires valid current approval.
Content, snapshots, and audit events are committed in the same SQLite transaction.

## API changes

- PUT /applications/{id}/content accepts application_message, cover_letter, expected_version.
- POST /applications/{id}/approve requires {"expected_version": N}.
- POST /applications/{id}/reject requires {"expected_version": N}.
- POST /applications/{id}/applied requires {"expected_version": N}.
- Application responses include content_version, approved_version, approved_at,
  and current_version_approved.
- Invalid workflow actions and stale versions return 409. Missing required request
  fields return 422. Missing applications return 404.
- Generation captures the content version before calling Gemini and refuses to overwrite
  a newer edit when the response arrives.

## Automated checks

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

These tests use temporary SQLite databases and mocked external services. They do not
load .env, access Gmail/Adzuna/Gemini, or use the real database. They cover HTTP endpoints,
review state, approval bypass attempts, stale edits, concurrent operations, transaction
rollback, persistence, and migration.

The optional browser smoke test requires Node.js, the playwright package, and Edge
(or set BROWSER_CHANNEL=chrome for Chrome):

```powershell
node tests/review_frontend.cjs
```

It serves the dashboard through intercepted requests with synthetic API responses and
never contacts the real application or external services.

## Manual acceptance check

Generate or open an existing application, edit both fields, save, and refresh. Confirm
that the text persists and the card requires review. Approve the current version and
confirm that Mark Applied appears. Change either field and save: approval must disappear
and Mark Applied must be unavailable. Approve again and mark applied manually. Inspect
history for the complete sequence. Finally, load the same application in two tabs, save
an edit in one, then try approving the older version in the other: it must be rejected.
