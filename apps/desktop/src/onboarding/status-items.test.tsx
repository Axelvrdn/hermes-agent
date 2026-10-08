import { QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { HermesConnection } from '@/global'
import { getLocalModelsJobs } from '@/hermes'
import { queryClient } from '@/lib/query-client'
import { setConnection } from '@/store/session'

import { $questionnaireDownload, LocalDownloadStatusItem } from './status-items'

// The jobs list is HTTP: answer it the way GET /api/local-models/jobs does mid-quickstart.
vi.mock('@/hermes', async importOriginal => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getLocalModelsJobs: vi.fn()
}))

// SAFETY: the jobs owner reads only baseUrl from the connection; the rest is window chrome.
const CONNECTION = { baseUrl: 'http://127.0.0.1:9119', isFullscreen: false, mode: 'local' } as HermesConnection

afterEach(() => {
  cleanup()
  $questionnaireDownload.set(null)
  setConnection(null)
  queryClient.clear()
  vi.clearAllMocks()
})

describe('LocalDownloadStatusItem', () => {
  it('shows the quickstart download with its percent once the backend connected after app start', async () => {
    vi.mocked(getLocalModelsJobs).mockResolvedValue({
      jobs: [
        {
          detail: '',
          done_bytes: 20,
          error: null,
          job_id: 'qs-1',
          kind: 'quickstart',
          model_id: 'qwen3.8-27b',
          percent: 20,
          phase: 'downloading',
          status: 'running',
          target: 'Qwen3.8 27B',
          total_bytes: 100
        }
      ]
    })

    // The status bar module loads before the backend connects; the questionnaire's Start comes later.
    setConnection(CONNECTION)
    $questionnaireDownload.set('Qwen3.8 27B')

    render(
      <QueryClientProvider client={queryClient}>
        <LocalDownloadStatusItem />
      </QueryClientProvider>
    )

    await act(async () => {
      await vi.waitFor(() => expect(getLocalModelsJobs).toHaveBeenCalled())
    })

    const item = await screen.findByRole('status')

    expect(item.textContent).toContain('Qwen3.8 27B')
    expect(item.textContent).toContain('20')
    expect(getLocalModelsJobs).toHaveBeenCalledWith(expect.objectContaining({ profile: 'default' }))
  })
})
