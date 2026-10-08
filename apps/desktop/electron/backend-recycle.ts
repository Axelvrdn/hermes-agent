/**
 * Recycle a Desktop-owned backend after a code-skew 503.
 *
 * Closing the local tunnel/child is not enough for SSH: `serve --isolated`
 * detaches with setsid/nohup, so a reconnect would reuse the still-alive
 * stale process via the lockfile. Kill the owned remote serve first (while
 * the SSH channel can still exec), then tear down the local child — the
 * same order as connection apply (#97046, #91668).
 */

export type RecycleOwnedBackendTarget = 'pool' | 'primary'

export interface RecycleOwnedBackendDeps {
  notifyApplied: () => void
  primaryProfile: string
  profile?: null | string
  teardownPool: (profile: string) => Promise<void>
  teardownPrimary: () => Promise<void>
  teardownSsh: (profile: string) => Promise<void>
}

export function recycleOwnedBackendTarget(
  profile: null | string | undefined,
  primaryProfile: string
): RecycleOwnedBackendTarget {
  const key = String(profile ?? '').trim()

  return !key || key === primaryProfile ? 'primary' : 'pool'
}

export async function recycleOwnedBackend(deps: RecycleOwnedBackendDeps): Promise<RecycleOwnedBackendTarget> {
  const target = recycleOwnedBackendTarget(deps.profile, deps.primaryProfile)
  const profile = String(deps.profile ?? '').trim()

  if (target === 'primary') {
    await deps.teardownSsh('')
    await deps.teardownPrimary()
    deps.notifyApplied()

    return target
  }

  await deps.teardownSsh(profile)
  await deps.teardownPool(profile)

  return target
}

/**
 * Pool keys to stop when a non-primary profile's backend is recycled. A "This
 * device" profile behind a remote primary is served by the shared local host
 * (`hostKey`) unless it has a backend of its own (an older runtime's
 * per-profile fallback): restarting only its old per-profile keys would
 * report success without touching the process the page refreshes against.
 * Profile DELETE keeps `ownKeys` alone, since it must never stop the host
 * that serves the other profiles.
 */
export function recyclePoolKeys(
  ownKeys: string[],
  {
    hostKey,
    hostServesProfile,
    isLive
  }: { hostKey: string; hostServesProfile: boolean; isLive: (key: string) => boolean }
): string[] {
  if (!hostServesProfile || ownKeys.some(key => !key.startsWith('local-rest::') && isLive(key))) {
    return ownKeys
  }

  return [...ownKeys, hostKey]
}
