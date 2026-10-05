import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  use: { baseURL: 'http://127.0.0.1:3000', browserName: 'webkit' },
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
