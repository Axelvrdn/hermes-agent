import { describe, expect, it, vi } from 'vitest'

import { recycleOwnedBackend, recycleOwnedBackendTarget, recyclePoolKeys } from './backend-recycle'

describe('recycleOwnedBackendTarget', () => {
  it('treats an empty or matching profile as the primary backend', () => {
    expect(recycleOwnedBackendTarget(undefined, 'default')).toBe('primary')
    expect(recycleOwnedBackendTarget('', 'default')).toBe('primary')
    expect(recycleOwnedBackendTarget('default', 'default')).toBe('primary')
  })

  it('treats any other named profile as a pooled backend', () => {
    expect(recycleOwnedBackendTarget('paid-ads', 'default')).toBe('pool')
  })
})

describe('recycleOwnedBackend', () => {
  it('kills the owned SSH serve before the primary child, then notifies apply', async () => {
    const events: string[] = []

    const target = await recycleOwnedBackend({
      notifyApplied: () => events.push('applied'),
      primaryProfile: 'default',
      profile: undefined,
      teardownPool: async () => {
        events.push('pool')
      },
      teardownPrimary: async () => {
        events.push('primary')
      },
      teardownSsh: async profile => {
        events.push(`ssh:${profile}`)
      }
    })

    expect(target).toBe('primary')
    expect(events).toEqual(['ssh:', 'primary', 'applied'])
  })

  it('recycles a pooled profile without tearing down the primary', async () => {
    const events: string[] = []

    const target = await recycleOwnedBackend({
      notifyApplied: () => events.push('applied'),
      primaryProfile: 'default',
      profile: 'paid-ads',
      teardownPool: async profile => {
        events.push(`pool:${profile}`)
      },
      teardownPrimary: async () => {
        events.push('primary')
      },
      teardownSsh: async profile => {
        events.push(`ssh:${profile}`)
      }
    })

    expect(target).toBe('pool')
    expect(events).toEqual(['ssh:paid-ads', 'pool:paid-ads'])
  })

  it('awaits SSH teardown before the local child even when SSH is slow', async () => {
    const events: string[] = []
    let releaseSsh!: () => void

    const sshGate = new Promise<void>(resolve => {
      releaseSsh = resolve
    })

    const run = recycleOwnedBackend({
      notifyApplied: () => events.push('applied'),
      primaryProfile: 'default',
      teardownPool: vi.fn(),
      teardownPrimary: async () => {
        events.push('primary')
      },
      teardownSsh: async () => {
        events.push('ssh-start')
        await sshGate
        events.push('ssh-done')
      }
    })

    await Promise.resolve()
    expect(events).toEqual(['ssh-start'])

    releaseSsh()
    await run

    expect(events).toEqual(['ssh-start', 'ssh-done', 'primary', 'applied'])
  })
})

describe('recyclePoolKeys', () => {
  const own = ['reviewer', 'conn:local::reviewer', 'local-rest::reviewer']

  it('adds the shared local host when it is what serves the profile', () => {
    // Remote primary: "This device" `reviewer` rides conn:local::default, not a key of its own.
    const keys = recyclePoolKeys(own, {
      hostKey: 'conn:local::default',
      hostServesProfile: true,
      isLive: key => key === 'conn:local::default'
    })

    expect(keys).toContain('conn:local::default')
  })

  it('keeps a profile on a backend of its own (older-runtime fallback) off the host', () => {
    const keys = recyclePoolKeys(own, {
      hostKey: 'conn:local::default',
      hostServesProfile: true,
      isLive: key => key === 'conn:local::reviewer' || key === 'conn:local::default'
    })

    expect(keys).toEqual(own)
  })

  it('never touches the host when it does not serve the profile', () => {
    expect(
      recyclePoolKeys(own, { hostKey: 'conn:local::default', hostServesProfile: false, isLive: () => true })
    ).toEqual(own)
  })
})
