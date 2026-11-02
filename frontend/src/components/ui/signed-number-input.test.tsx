import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { cleanSigned, SignedNumberInput } from '@/components/ui/signed-number-input'

function Harness() {
  const [value, setValue] = useState('')
  return <><SignedNumberInput aria-label="Temperature" value={value} onChange={setValue} /><output>{value}</output></>
}

describe('SignedNumberInput', () => {
  it('cleans what is typed into a number', () => {
    expect([cleanSigned('-18,5'), cleanSigned('−18'), cleanSigned('4a.2.1'), cleanSigned('--3'), cleanSigned('')]).toEqual(['-18.5', '-18', '4.21', '-3', ''])
  })

  it('has a button for the minus sign, which the iPhone number keypad lacks', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const field = screen.getByLabelText('Temperature') as HTMLInputElement
    expect(field.inputMode).toBe('decimal')
    await user.type(field, '18')
    await user.click(screen.getByRole('button', { name: 'Make negative' }))
    expect(screen.getByRole('status').textContent).toBe('-18')
    await user.click(screen.getByRole('button', { name: 'Make positive' }))
    expect(screen.getByRole('status').textContent).toBe('18')
  })
})
