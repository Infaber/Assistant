import { defineConfig } from '@playwright/test';

const baseURL = process.env.ARIANA_TEST_URL || 'http://127.0.0.1:3000';

export default defineConfig({
  testDir: './tests/browser',
  use: { baseURL, browserName: 'webkit' },
  webServer: {
    command: 'npm run dev',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
