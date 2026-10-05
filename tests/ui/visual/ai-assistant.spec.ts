/**
 * Canvas visual regression: ai-assistant (III-1…III-3, III-5, III-6, III-8).
 * Generated from docs/ui/canvas-registry.yaml — do not edit by hand;
 * re-run: python tests/ui/visual/generate_from_registry.py
 */
import { test } from '../../../frontend/node_modules/@playwright/test/index.js'
import { assertCanvasScreenshot, openStory } from './helpers'

const STORY_ID = 'assistant-window--chat-with-sources'
const SNAPSHOT = 'ai-assistant.png'

test('ai-assistant visual baseline', async ({ page }) => {
  await openStory(page, STORY_ID)
  await assertCanvasScreenshot(page, SNAPSHOT)
})
