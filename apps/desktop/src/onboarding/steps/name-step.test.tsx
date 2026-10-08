import type { MachineFactsResult } from '@hermes/shared'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { closeQuestionnaire, openQuestionnaire, setFacts } from '../store'

import { NameStep } from './questions'

afterEach(() => {
  cleanup()
  closeQuestionnaire('skipped')
})

// machine.facts for a Windows local account with no display name (full_name null), as on the walk.
const NAMELESS: MachineFactsResult = {
  full_name: null,
  has_nvidia_gpu: true,
  is_spark: false,
  locale: 'en-US',
  machine: { cpu_model: 'Intel Core i7-14700K', os_family: 'windows', os_release: '11', ram_gb: 64 },
  machine_kind: 'PC'
}

describe('NameStep', () => {
  it('asks for the name in a plain field when the OS has no name to offer', () => {
    openQuestionnaire()
    setFacts({ machine: NAMELESS })
    render(<NameStep />)

    const field = screen.getByPlaceholderText('Your name')

    expect(field.ownerDocument.activeElement).toBe(field)
    expect(screen.queryByPlaceholderText('Other (type your answer)')).toBeNull()
  })

  it('offers the OS full name as a pill, with Other beside it', () => {
    openQuestionnaire()
    setFacts({ machine: { ...NAMELESS, full_name: 'Sid Balyan' } })
    render(<NameStep />)

    expect(screen.getByRole('button', { name: /Sid/ })).toBeTruthy()
    expect(screen.getByPlaceholderText('Other (type your answer)')).toBeTruthy()
  })
})
