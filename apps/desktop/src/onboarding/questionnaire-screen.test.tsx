import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { $freeTierStatus } from '@/store/free-tier'
import { markQuestionnaireDecided } from '@/store/onboarding-presence'

import type { OnboardingRequester } from './due'
import { FIXTURES } from './fixtures.test-util'
import { Questionnaire, QuestionnaireScreen } from './Questionnaire'
import { $questionnaire, closeQuestionnaire, openQuestionnaire, setFacts, skipStep } from './store'

/** A backend that never answers: whatever the user pressed stays in flight. */
const silent: OnboardingRequester = <T,>() => new Promise<T>(() => {})

/** The review screen; the step change's exit transition runs before it mounts. */
async function renderReview(): Promise<HTMLElement> {
  render(
    <>
      <Questionnaire enabled={false} openDefaultChat={async () => 'runtime-1'} requestGateway={silent} />
      <QuestionnaireScreen refreshReadiness={async () => {}} />
    </>
  )

  act(() => {
    setFacts(FIXTURES.spark)

    for (let stepId = $questionnaire.get().stepId; stepId; stepId = $questionnaire.get().stepId) {
      skipStep(stepId)
    }
  })

  return screen.findByRole('button', { name: 'Start' })
}

beforeEach(() => {
  markQuestionnaireDecided()
  $freeTierStatus.set(null)
  openQuestionnaire()
})

afterEach(() => {
  cleanup()
  closeQuestionnaire('skipped')
})

describe('QuestionnaireScreen while Start or Skip is in flight', () => {
  it('locks the answer trail while Start waits, so the prompt it sends is the one on screen', async () => {
    fireEvent.click(await renderReview())

    const chips = screen.getAllByRole('button', { name: 'Change this answer' })

    expect(chips.length).toBeGreaterThan(0)
    expect(chips.every(chip => chip.hasAttribute('disabled'))).toBe(true)
  })

  it('locks Start, Back and the trail while Skip is saving', async () => {
    const start = await renderReview()

    fireEvent.click(screen.getByRole('button', { name: 'Skip setup' }))

    expect(start.hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: 'Back' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getAllByRole('button', { name: 'Change this answer' }).every(chip => chip.hasAttribute('disabled'))).toBe(
      true
    )
  })
})
