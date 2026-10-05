import type { Preview } from '@storybook/react-vite'
import '../src/index.css'

const preview: Preview = {
  parameters: {
    controls: { expanded: true },
    a11y: { test: 'error' },
    backgrounds: { default: 'light' },
    layout: 'centered',
  },
}

export default preview
