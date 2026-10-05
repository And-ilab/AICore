import { defineConfig, devices } from '@playwright/test'

/** P8-09 / FR visual gate: fail when screenshot differs by more than 0.1%. */
const MAX_DIFF_PIXEL_RATIO = 0.001

const sharedUse = {
  ...devices['Desktop Chrome'],
  baseURL: 'http://127.0.0.1:6006',
  colorScheme: 'light' as const,
  reducedMotion: 'reduce' as const,
}

export default defineConfig({
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 120_000,
  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: MAX_DIFF_PIXEL_RATIO,
      animations: 'disabled',
    },
  },
  webServer: {
    command: 'npm run storybook -- --ci --no-open',
    url: 'http://127.0.0.1:6006',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: 'ui',
      testDir: '../tests/ui',
      testIgnore: ['**/visual/**'],
      snapshotPathTemplate: '../tests/ui/__snapshots__/{arg}{ext}',
      use: {
        ...sharedUse,
        viewport: { width: 900, height: 700 },
      },
    },
    {
      // Canvas-registry visual regression (P8-09). CI job: ui-visual.
      name: 'visual',
      testDir: '../tests/ui/visual',
      testMatch: '**/*.spec.ts',
      snapshotPathTemplate: '../tests/ui/visual/__snapshots__/{arg}{ext}',
      use: {
        ...sharedUse,
        viewport: { width: 1280, height: 800 },
      },
    },
  ],
})
