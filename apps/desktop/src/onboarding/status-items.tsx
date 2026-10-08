/**
 * The questionnaire's background work, in the status bar (it stays visible under the overlay):
 * the free account while it is being made, and the local model download started after Start.
 */

import { useStore } from '@nanostores/react'
import { atom } from 'nanostores'

import { runQuickstart } from '@/app/settings/local-models-actions'
import { AnimatedInt } from '@/components/ui/diff-count'
import { Progress } from '@/components/ui/progress'
import { runtimeTranslations, useI18n } from '@/i18n'
import { queryClient } from '@/lib/query-client'
import { $freeTierStatus, freeTierSetupFailure } from '@/store/free-tier'
import {
  localModelsOwner,
  runningModelDownloads,
  useLocalModelsOwner,
  useLocalRuntimeJobs
} from '@/store/local-runtime-jobs'

import { freeAccountState } from './facts'
import type { LocalFit } from './flow'
import { $questionnaireOpen } from './store'

/** The job id of the questionnaire's quickstart; `null` when none started (or the POST was refused). */
export const $questionnaireDownload = atom<null | string>(null)

/** Start's local answer: quickstart `model` in the default profile, the way Settings > Local Models starts one. */
export async function startQuestionnaireQuickstart(model: LocalFit): Promise<void> {
  const jobId = await runQuickstart(
    { client: queryClient, copy: runtimeTranslations().settings.localModels, owner: localModelsOwner('default') },
    model.id
  )

  $questionnaireDownload.set(jobId)
}

const ITEM_CLASS = 'flex h-full items-center gap-1.5 px-1.5 text-[0.6875rem]'

/** "Setting up your free account" until `setup.ready`, then "Nous · free tier"; only while the questionnaire is open. */
export function FreeAccountStatusItem() {
  const { t } = useI18n()
  const open = useStore($questionnaireOpen)
  const status = useStore($freeTierStatus)
  const copy = t.questionnaire.status

  if (!open || !status?.enabled) {
    return null
  }

  const state = freeAccountState(status)

  if (state === 'ready') {
    return <span className={ITEM_CLASS}>{copy.ready}</span>
  }

  if (state === 'failed') {
    return <span className={`${ITEM_CLASS} text-destructive`}>{copy.unavailable}</span>
  }

  const label = freeTierSetupFailure(status) ? copy.stillSettingUp : copy.settingUp

  return (
    <span className={ITEM_CLASS} role="status">
      <span>{label}</span>
      <Progress animated aria-label={label} className="w-12" indeterminate size="sm" />
    </span>
  )
}

const ENGINE_PHASES = new Set(['downloading-runtime', 'unpacking-runtime', 'verifying-runtime'])

function DownloadProgress({ jobId }: { jobId: string }) {
  const { t } = useI18n()
  // Resolved on render, not at import: an owner minted before the backend connected is never live.
  const owner = useLocalModelsOwner('default')
  // Only Start's own job: a later download from Settings is not the questionnaire's.
  const job = useLocalRuntimeJobs(owner, jobs => runningModelDownloads(jobs).find(row => row.job_id === jobId) ?? null)

  if (!job) {
    return null
  }

  const percent = Math.round(job.percent ?? (job.total_bytes ? (job.done_bytes / job.total_bytes) * 100 : 0))

  // Quickstart fetches the engine first, then the model; each stage counts its own percent from 0.
  const label = ENGINE_PHASES.has(job.phase)
    ? t.questionnaire.status.downloadingEngine
    : t.questionnaire.status.downloading(job.target)

  return (
    <span className={ITEM_CLASS} role="status">
      <span className="truncate">{label}</span>
      <Progress aria-label={label} className="w-14" size="sm" value={percent / 100} />
      <span className="tabular-nums">
        <AnimatedInt value={percent} />%
      </span>
    </span>
  )
}

/** The local model the questionnaire started downloading, with a bar, until the job settles. */
export function LocalDownloadStatusItem() {
  const jobId = useStore($questionnaireDownload)

  return jobId ? <DownloadProgress jobId={jobId} /> : null
}
