import { test, expect } from '@playwright/test';

test('real local token route accepts the browser origin', async ({ page }) => {
  await page.goto('/');
  const status = await page.evaluate(async () => {
    const response = await fetch('/api/connection', { method: 'POST' });
    return response.status;
  });
  // Credentials may be absent or access-code protected; neither should cause
  // an origin rejection for a same-origin request through the real Next server.
  expect([201, 401, 503]).toContain(status);
});

test('shows the workspace, drafts suggested prompts, and fits a phone screen', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'At your command.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Send message' })).toBeDisabled();
  await page.getByRole('button', { name: 'Think it through' }).click();
  await expect(page.getByRole('textbox', { name: 'Message Ariana' })).toHaveValue('Can you help me think through an idea?');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('sends the access code only when starting, shows server errors, and allows retry', async ({ page }) => {
  const headers: string[] = [];
  await page.route('**/api/connection', async (route) => {
    headers.push(route.request().headers().authorization);
    await route.fulfill({ status: 503, json: { error: 'Add your LiveKit credentials to frontend/.env.local, then restart the frontend.' } });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Connection settings' }).click();
  await page.getByLabel('Access code', { exact: true }).fill('workspace-secret');
  await page.getByRole('button', { name: 'Save settings' }).click();
  expect(headers).toEqual([]);
  await page.getByRole('button', { name: 'Text', exact: true }).click();
  await page.getByRole('button', { name: 'Start conversation' }).click();
  await expect(page.getByRole('region', { name: 'Conversation', exact: true }).getByRole('alert')).toContainText('Add your LiveKit credentials');
  await expect(page.getByRole('button', { name: 'Start conversation' })).toBeEnabled();
  expect(headers).toEqual(['Bearer workspace-secret']);
  await page.getByRole('button', { name: 'Start conversation' }).click();
  await expect.poll(() => headers.length).toBe(2);
});

test('cancels an in-flight connection without displaying an error', async ({ page }) => {
  await page.route('**/api/connection', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    await route.fulfill({ status: 503, json: { error: 'Should not be shown after cancellation' } }).catch(() => {});
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Text', exact: true }).click();
  await page.getByRole('button', { name: 'Start conversation' }).click();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Start conversation' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Conversation', exact: true }).getByRole('alert')).toHaveCount(0);
});


test('capability commands draft without sending and focus mode returns to input', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/connection', async (route) => { requests++; await route.fulfill({ status: 503, json: { error: 'Connection unavailable for this test.' } }); });
  await page.goto('/');
  await page.getByRole('button', { name: 'Memory A little more personal' }).click();
  await expect(page.getByRole('textbox', { name: 'Message Ariana' })).toHaveValue('What do you remember about me?');
  await expect(page.getByRole('textbox', { name: 'Message Ariana' })).toBeFocused();
  await page.getByRole('button', { name: 'Enter focus mode' }).click();
  await expect(page.getByRole('region', { name: 'Conversation', exact: true })).toBeHidden();
  await page.keyboard.press('Control+k');
  await expect(page.getByRole('region', { name: 'Conversation', exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Message Ariana' })).toBeFocused();
  expect(requests).toBe(0);
  await page.getByRole('button', { name: 'Enter focus mode' }).click();
  await page.getByRole('button', { name: 'Text', exact: true }).click();
  await page.getByRole('button', { name: 'Start conversation' }).click();
  await expect(page.getByRole('region', { name: 'Conversation', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Conversation', exact: true }).getByRole('alert')).toContainText('Connection unavailable for this test.');
  await expect(page.getByRole('button', { name: 'Start conversation' })).toBeEnabled();
});


test('activity starts empty, stays responsive on mobile, and drafting returns to conversation', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Activity 0', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Waiting for a task.' })).toBeVisible();
  await expect(page.getByRole('log', { name: 'Action activity' })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Think it through' }).click();
  await expect(page.getByRole('button', { name: 'Conversation', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('textbox', { name: 'Message Ariana' })).toBeFocused();
});

test('stages files before connecting, supports pasted pictures, and removes previews', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Choose attachments').setInputFiles({ name: 'lab.txt', mimeType: 'text/plain', buffer: Buffer.from('Robotics Friday 14:00') });
  await expect(page.getByLabel('Attachments ready to send')).toContainText('lab.txt');
  await expect(page.getByRole('button', { name: 'Send message', exact: true })).toBeDisabled();
  await page.getByLabel('Message Ariana').evaluate(input => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([new Uint8Array([137, 80, 78, 71])], 'pasted.png', { type: 'image/png' }));
    input.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, clipboardData: transfer }));
  });
  await expect(page.getByRole('img', { name: 'Preview of pasted.png' })).toBeVisible();
  await page.getByRole('button', { name: 'Remove lab.txt', exact: true }).click();
  await expect(page.getByLabel('Attachments ready to send')).not.toContainText('lab.txt');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('rejects unsupported attachments and shows check-ins without silently connecting', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/connection', async route => { requests++; await route.fulfill({ status: 503 }); });
  await page.goto('/');
  await page.getByLabel('Choose attachments').setInputFiles({ name: 'archive.zip', mimeType: 'application/zip', buffer: Buffer.from('binary') });
  await expect(page.getByRole('region', { name: 'Conversation', exact: true }).getByRole('alert')).toContainText('use a picture');
  await expect(page.getByRole('switch', { name: 'Let Ariana start conversations' })).toBeDisabled();
  await expect(page.getByRole('switch', { name: 'Let Ariana start conversations' })).toHaveAttribute('aria-checked', 'false');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('region', { name: 'Proactive check-ins' })).toBeVisible();
  expect(requests).toBe(0);
});

test('native companion automatically connects in text mode and exposes background check-ins', async ({ page }) => {
  const authorizations: string[] = [];
  await page.addInitScript(() => { window.arianaDesktop = { desktop: true, accessCode: 'native-test-code' }; });
  await page.route('**/api/connection', async route => {
    authorizations.push(route.request().headers().authorization);
    await route.fulfill({ status: 503, json: { error: 'Mock native connection unavailable' } });
  });
  await page.goto('/');
  await expect(page.getByRole('region', { name: 'Conversation', exact: true }).getByRole('alert')).toContainText('Mock native connection unavailable');
  expect(authorizations).toEqual(['Bearer native-test-code']);
  await expect(page.getByRole('button', { name: 'Text', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('region', { name: 'Proactive check-ins' })).toContainText('Close the window');
  await expect(page.getByRole('switch', { name: 'Let Ariana start conversations' })).toHaveAttribute('aria-checked', 'true');
});
