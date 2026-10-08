import { QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { HermesConnection } from '@/global'
import { queryClient } from '@/lib/query-client'
import { setConnection } from '@/store/session'
import { installRestBridge } from '@/test/rest-bridge'

import { $questionnaireDownload, LocalDownloadStatusItem, startQuestionnaireQuickstart } from './status-items'

// SAFETY: the jobs owner reads only baseUrl from the connection; the rest is window chrome.
const CONNECTION = { baseUrl: 'http://127.0.0.1:9119', isFullscreen: false, mode: 'local' } as HermesConnection

// GET /api/local-models/jobs mid-quickstart, as the Windows run answered it.
const QUICKSTART_JOB = {
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

afterEach(() => {
  cleanup()
  $questionnaireDownload.set(null)
  setConnection(null)
  queryClient.clear()
})

describe('LocalDownloadStatusItem', () => {
  it('shows the quickstart download with its percent once the backend connected after app start', async () => {
    const api = installRestBridge(request => (request.path === '/api/local-models/jobs' ? { jobs: [QUICKSTART_JOB] } : {}))

    // The status bar module loads before the backend connects; the questionnaire's Start comes later.
    setConnection(CONNECTION)
    $questionnaireDownload.set('Qwen3.8 27B')

    render(
      <QueryClientProvider client={queryClient}>
        <LocalDownloadStatusItem />
      </QueryClientProvider>
    )

    const item = await screen.findByRole('status')

    expect(item.textContent).toContain('Qwen3.8 27B')
    await waitFor(() => expect(item.textContent).toContain('20'))
    expect(api).toHaveBeenCalledWith(expect.objectContaining({ path: '/api/local-models/jobs', profile: 'default' }))
  })

  it("shows the download Start's quickstart created, though the first jobs read came before the job", async () => {
    let answerQuickstart = () => {}
    let jobCreated = false

    // The backend creates the job while it handles the POST; until then the jobs list is empty.
    const api = installRestBridge(request => {
      if (request.path === '/api/local-models/quickstart') {
        return new Promise<object>(resolve => {
          answerQuickstart = () => {
            jobCreated = true
            resolve({ job_id: 'qs-1', model_id: 'qwen3.8-27b' })
          }
        })
      }

      return request.path === '/api/local-models/jobs' ? { jobs: jobCreated ? [QUICKSTART_JOB] : [] } : {}
    })

    setConnection(CONNECTION)
    render(
      <QueryClientProvider client={queryClient}>
        <LocalDownloadStatusItem />
      </QueryClientProvider>
    )

    const started = startQuestionnaireQuickstart({ id: 'qwen3.8-27b', name: 'Qwen3.8 27B' })

    await waitFor(() => expect(api).toHaveBeenCalledWith(expect.objectContaining({ path: '/api/local-models/jobs' })))
    answerQuickstart()
    await started

    const item = await screen.findByRole('status')

    expect(item.textContent).toContain('Qwen3.8 27B')
    await waitFor(() => expect(item.textContent).toContain('20'))
    expect(api).toHaveBeenCalledWith(
      expect.objectContaining({ body: { model_id: 'qwen3.8-27b' }, path: '/api/local-models/quickstart', profile: 'default' })
    )
  })
})
