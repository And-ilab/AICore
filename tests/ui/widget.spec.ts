import {
  expect,
  test,
  type Page,
} from '../../frontend/node_modules/@playwright/test/index.js'

async function openWidgetSample(page: Page) {
  await page.goto('/widget/sample.html')
  await page.evaluate(() => document.fonts.ready)
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation: none !important;
        caret-color: transparent !important;
        transition: none !important;
      }
    `,
  })
  await expect(page.locator('#bb-chat-widget-host')).toBeAttached({
    timeout: 10_000,
  })
}

test('embeddable widget opens on sample bank page (FR-CC-09)', async ({ page }) => {
  await openWidgetSample(page)
  const host = page.locator('#bb-chat-widget-host')
  await expect(host).toHaveAttribute('data-widget-id', 'site-belarusbank')

  await host.getByTestId('widget-fab').click()
  const panel = host.getByTestId('widget-panel')
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('Онлайн-консультант')
  await expect(panel).toContainText('Беларусбанк')
  await expect(panel).toContainText('Операторы онлайн')
  await expect(panel).toContainText('Задайте Ваш вопрос')
  await expect(host.getByTestId('widget-name')).toBeVisible()
  await expect(host.getByTestId('widget-last-name')).toBeVisible()
  await expect(host.getByTestId('widget-phone')).toBeVisible()
  await expect(host.getByTestId('widget-question')).toBeVisible()

  await host.getByTestId('widget-name').fill('Анна')
  await host.getByTestId('widget-last-name').fill('Козлова')
  await host.getByTestId('widget-phone').fill('+375 29 123-45-67')
  await host.getByTestId('widget-question').fill('Лимит снятия?')
  await host.getByTestId('widget-start').click()
  await expect(host.getByTestId('widget-messages')).toBeVisible()
  await expect(host.getByTestId('widget-messages')).toContainText('Лимит снятия?')
  await expect(panel).not.toContainText('Мария Соколова')
  await expect(host.getByTestId('widget-messages')).toContainText('Ожидаем ответа оператора')
})

test('chat-widget-sample', async ({ page }) => {
  await openWidgetSample(page)
  const host = page.locator('#bb-chat-widget-host')
  await host.getByTestId('widget-fab').click()
  await host.getByTestId('widget-name').fill('Анна')
  await host.getByTestId('widget-last-name').fill('Козлова')
  await host.getByTestId('widget-phone').fill('+375 29 123-45-67')
  await host.getByTestId('widget-question').fill('Лимит снятия?')
  await host.getByTestId('widget-start').click()
  await expect(host.getByTestId('widget-messages')).toBeVisible()
  await expect(page.locator('body')).toHaveScreenshot('chat-widget-sample.png', {
    animations: 'disabled',
    scale: 'css',
  })
})
