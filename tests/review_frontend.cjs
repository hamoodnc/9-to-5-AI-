// Offline browser smoke test: all page/API responses are synthetic.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
    const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'msedge', headless: true });
    try {
        const page = await browser.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('dialog', dialog => dialog.accept());
        const html = fs.readFileSync(path.join(__dirname, '../frontend/index.html'), 'utf8');
        const fixture = id => ({ id, title: 'Synthetic support role', company: 'Example', location: 'Ottawa',
            url: 'https://example.com', match_score: 70, status: 'ready_for_review',
            generation_status: 'generated', approval_status: 'pending', content_version: 1,
            approved_version: null, approved_at: null, current_version_approved: false,
            application_message: 'Original message', cover_letter: 'Original letter' });
        const applications = [fixture(1), fixture(2)];
        const requests = [];
        await page.route('**/*', async route => {
            const request = route.request();
            const url = new URL(request.url());
            if (url.pathname === '/dashboard') return route.fulfill({ contentType: 'text/html', body: html });
            if (url.pathname === '/applications') return route.fulfill({ json: applications });
            const match = url.pathname.match(/^\/applications\/(\d+)\/(.+)$/);
            if (!match) return route.abort();
            const a = applications.find(a => a.id === Number(match[1]));
            const action = match[2];
            const body = request.postDataJSON();
            requests.push({ action, body, method: request.method() });
            if (body.expected_version !== a.content_version) {
                return route.fulfill({ status: 409, json: { detail: 'Content changed since you loaded it. Reload and review the latest version.' } });
            }
            if (action === 'content') {
                Object.assign(a, body, { content_version: a.content_version + 1,
                    approved_version: null, approved_at: null, current_version_approved: false,
                    approval_status: 'pending', status: 'ready_for_review' });
            } else if (action === 'approve') {
                Object.assign(a, { approved_version: a.content_version, approved_at: 'synthetic',
                    current_version_approved: true, approval_status: 'approved', status: 'approved' });
            } else if (action === 'applied') {
                assert.equal(a.current_version_approved, true);
                a.status = 'applied';
            } else if (action === 'reject') {
                Object.assign(a, { current_version_approved: false, approval_status: 'needs_changes', status: 'ready_for_review' });
            }
            return route.fulfill({ json: a });
        });
        await page.goto('http://review.test/dashboard');
        const first = page.locator('#application-1');
        const second = page.locator('#application-2');
        await first.locator('.message-editor').waitFor();
        assert.equal(await first.locator('.message-editor').inputValue(), 'Original message');
        assert.equal(await first.locator('.mark-applied').count(), 0);
        await second.locator('.message-editor').fill('Unsaved second application');
        await first.locator('.message-editor').fill('Edited message');
        await first.locator('.letter-editor').fill('Edited letter');
        assert.equal(await first.locator('.approve-version').isDisabled(), true);
        await first.locator('.save-content').click();
        await page.waitForFunction(() => document.querySelector('#application-1 .generated-content').textContent.includes('version 2'));
        assert.equal(requests[0].method, 'PUT');
        assert.equal(requests[0].body.expected_version, 1);
        assert.equal(await second.locator('.message-editor').inputValue(), 'Unsaved second application');
        await first.locator('.approve-version').click();
        await first.locator('.mark-applied').waitFor();
        assert.equal(await first.locator('.version-approval').textContent(), 'Approved - version 2');
        await first.locator('.letter-editor').fill('Changed after approval');
        assert.equal(await first.locator('.mark-applied').isDisabled(), true);
        await first.locator('.save-content').click();
        await first.locator('.approve-version').waitFor();
        assert.equal(await first.locator('.mark-applied').count(), 0);
        await first.locator('.needs-changes').click();
        await page.waitForFunction(() => document.querySelector('#application-1 .application-meta').textContent.includes('needs_changes'));
        assert.equal(await first.locator('.message-editor').isEditable(), true);
        assert.equal(await first.locator('.approve-version').isEnabled(), true);
        assert.equal(await first.locator('.regenerate-content').isEnabled(), true);
        // Simulate another browser editing the saved version.
        applications[0].content_version += 1;
        await first.locator('.message-editor').fill('Keep my conflicting edit');
        await first.locator('.save-content').click();
        await page.waitForFunction(() => document.querySelector('#application-1 .review-feedback').textContent.includes('Content changed'));
        assert.equal(await first.locator('.message-editor').inputValue(), 'Keep my conflicting edit');
        assert.equal(await first.locator('.approve-version').isDisabled(), true);
        assert.deepEqual(errors, []);
        console.log('PASS: browser editing, version approval, invalidation, Needs Changes, stale conflicts, and preservation of other unsaved cards');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
