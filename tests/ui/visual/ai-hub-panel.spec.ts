/**
 * Canvas visual regression: ai-hub-panel (I-1).
 * Generated from docs/ui/canvas-registry.yaml — do not edit by hand;
 * re-run: python tests/ui/visual/generate_from_registry.py
 */
import { test } from '../../../frontend/node_modules/@playwright/test/index.js'
import { assertCanvasScreenshot, openStory } from './helpers'

const STORY_ID = 'ai-hub-panel--default-assistant'
const SNAPSHOT = 'ai-hub-panel.png'

test('ai-hub-panel visual baseline', async ({ page }) => {
  await openStory(page, STORY_ID)
  await assertCanvasScreenshot(page, SNAPSHOT)
})
