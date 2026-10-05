/**
 * Canvas visual regression: online-chat (II-3, II-6…II-12).
 * Generated from docs/ui/canvas-registry.yaml — do not edit by hand;
 * re-run: python tests/ui/visual/generate_from_registry.py
 */
import { test } from '../../../frontend/node_modules/@playwright/test/index.js'
import { assertCanvasScreenshot, openStory } from './helpers'

const STORY_ID = 'online-chat-arm--operator-workspace'
const SNAPSHOT = 'online-chat.png'

test('online-chat visual baseline', async ({ page }) => {
  await openStory(page, STORY_ID)
  await assertCanvasScreenshot(page, SNAPSHOT)
})
