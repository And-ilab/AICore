/**
 * Canvas visual regression: ai-hub-settings (I-2, II-4, II-5, III-4, III-7, IV-4, IV-5).
 * Generated from docs/ui/canvas-registry.yaml — do not edit by hand;
 * re-run: python tests/ui/visual/generate_from_registry.py
 */
import { test } from '../../../frontend/node_modules/@playwright/test/index.js'
import { assertCanvasScreenshot, openStory } from './helpers'

const STORY_ID = 'ai-hub-admin-shell--default'
const SNAPSHOT = 'ai-hub-settings.png'

test('ai-hub-settings visual baseline', async ({ page }) => {
  await openStory(page, STORY_ID)
  await assertCanvasScreenshot(page, SNAPSHOT)
})
