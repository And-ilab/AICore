/**
 * Canvas visual regression: ocr-documents (IV-1…IV-3).
 * Generated from docs/ui/canvas-registry.yaml — do not edit by hand;
 * re-run: python tests/ui/visual/generate_from_registry.py
 */
import { test } from '../../../frontend/node_modules/@playwright/test/index.js'
import { assertCanvasScreenshot, openStory } from './helpers'

const STORY_ID = 'ai-hub-panel--documents-upload-flow'
const SNAPSHOT = 'ocr-documents.png'

test('ocr-documents visual baseline', async ({ page }) => {
  await openStory(page, STORY_ID)
  await assertCanvasScreenshot(page, SNAPSHOT)
})
