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
  await expect(page.getByRole('heading', { name: 'A space to think together.' })).toBeVisible();
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
