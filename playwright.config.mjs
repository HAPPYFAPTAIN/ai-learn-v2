import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser',
  outputDir: 'output/runtime/browser',
  use: {baseURL: 'http://127.0.0.1:7863'},
  webServer: {
    command: 'python scripts/preview_home_rail.py --port 7863',
    url: 'http://127.0.0.1:7863/le-presentation.css',
    reuseExistingServer: false,
    env: { GRADIO_ANALYTICS_ENABLED: 'False' },
  },
});
