/**
 * Canvas visual regression: internal-user-kc (II-KC).
 * Generated from docs/ui/canvas-registry.yaml — do not edit by hand;
 * re-run: python tests/ui/visual/generate_from_registry.py
 */
import { test } from '../../../frontend/node_modules/@playwright/test/index.js'
import { assertCanvasScreenshot, openStory } from './helpers'

const STORY_ID = 'internal-kc-test-dialog--prompt-harness'
const SNAPSHOT = 'internal-user-kc.png'

test('internal-user-kc visual baseline', async ({ page }) => {
  await openStory(page, STORY_ID)
  await assertCanvasScreenshot(page, SNAPSHOT)
})
