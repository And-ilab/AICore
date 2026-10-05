import type { Meta, StoryObj } from '@storybook/react-vite'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from './Table'

const meta = {
  title: 'Foundation/Table',
  component: Table,
} satisfies Meta<typeof Table>

export default meta
type Story = StoryObj<typeof meta>

export const Basic: Story = {
  render: () => (
    <Table caption="Каталог записей ASR">
      <TableHead>
        <TableRow>
          <TableHeaderCell>Дата</TableHeaderCell>
          <TableHeaderCell>Канал</TableHeaderCell>
          <TableHeaderCell>Оператор</TableHeaderCell>
          <TableHeaderCell>Confidence</TableHeaderCell>
        </TableRow>
      </TableHead>
      <TableBody>
        <TableRow>
          <TableCell>27.07.2026 12:00</TableCell>
          <TableCell>Телефония</TableCell>
          <TableCell>Иванов И.И.</TableCell>
          <TableCell>96%</TableCell>
        </TableRow>
        <TableRow>
          <TableCell>27.07.2026 13:10</TableCell>
          <TableCell>Онлайн-чат</TableCell>
          <TableCell>Петрова А.С.</TableCell>
          <TableCell>18%</TableCell>
        </TableRow>
      </TableBody>
    </Table>
  ),
}
