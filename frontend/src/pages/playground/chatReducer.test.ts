import { describe, expect, it } from 'vitest'
import { chatReducer, turnsToHistory, type ChatAction } from './chatReducer'

// Shorthand for the common 'send' action shape used across these tests.
function send(userId: string, assistantId: string, content: string): ChatAction {
  return { type: 'send', userId, assistantId, content, hadSchema: false, modelId: 'gpt2', backend: 'api' }
}

describe('chatReducer', () => {
  it('appends a user turn and a streaming assistant placeholder on send', () => {
    const state = chatReducer([], send('u1', 'a1', 'hi'))

    expect(state).toHaveLength(2)
    expect(state[0]).toMatchObject({ id: 'u1', role: 'user', content: 'hi', streaming: false, modelId: 'gpt2', backend: 'api' })
    expect(state[1]).toMatchObject({ id: 'a1', role: 'assistant', content: '', streaming: true, hadSchema: false, modelId: 'gpt2', backend: 'api' })
  })

  it('accumulates deltas onto the streaming assistant turn only', () => {
    let state = chatReducer([], send('u1', 'a1', 'hi'))
    state = chatReducer(state, { type: 'delta', id: 'a1', text: 'Hel' })
    state = chatReducer(state, { type: 'delta', id: 'a1', text: 'lo' })

    expect(state[1].content).toBe('Hello')
    expect(state[0].content).toBe('hi') // the user turn is untouched
  })

  it('done attaches usage, tools called, retries and metrics, and stops streaming', () => {
    let state = chatReducer([], send('u1', 'a1', 'hi'))
    state = chatReducer(state, { type: 'delta', id: 'a1', text: 'Hello' })
    state = chatReducer(state, {
      type: 'done',
      id: 'a1',
      usage: { prompt_tokens: 10, completion_tokens: 5 },
      toolsCalled: ['calculator'],
      retries: 1,
      metrics: { ttftMs: 120, tokensPerSec: 25, totalMs: 400 },
    })

    expect(state[1]).toMatchObject({
      content: 'Hello',
      streaming: false,
      usage: { prompt_tokens: 10, completion_tokens: 5 },
      toolsCalled: ['calculator'],
      retries: 1,
      metrics: { ttftMs: 120, tokensPerSec: 25, totalMs: 400 },
    })
  })

  it('error stops streaming and records the error for that turn', () => {
    let state = chatReducer([], send('u1', 'a1', 'hi'))
    const error = new Error('boom')
    state = chatReducer(state, { type: 'error', id: 'a1', error })

    expect(state[1]).toMatchObject({ streaming: false, error })
  })

  it('stop settles the turn without an error, flagged as stopped', () => {
    let state = chatReducer([], send('u1', 'a1', 'hi'))
    state = chatReducer(state, { type: 'stop', id: 'a1' })

    expect(state[1]).toMatchObject({ streaming: false, stopped: true, error: null })
  })

  it('reset clears the transcript for New chat', () => {
    let state = chatReducer([], send('u1', 'a1', 'hi'))
    state = chatReducer(state, { type: 'reset' })

    expect(state).toEqual([])
  })
})

describe('turnsToHistory', () => {
  it('includes settled user/assistant pairs in order', () => {
    let state = chatReducer([], send('u1', 'a1', 'first'))
    state = chatReducer(state, { type: 'done', id: 'a1', usage: null, toolsCalled: [], retries: 0, metrics: { ttftMs: 1, tokensPerSec: null, totalMs: 1 } })
    state = chatReducer(state, { type: 'delta', id: 'a1', text: 'reply one' })

    expect(turnsToHistory(state)).toEqual([
      { role: 'user', content: 'first' },
      { role: 'assistant', content: 'reply one' },
    ])
  })

  it('drops an errored pair and a stopped pair, keeping surrounding settled pairs', () => {
    let state = chatReducer([], send('u1', 'a1', 'first'))
    state = chatReducer(state, { type: 'delta', id: 'a1', text: 'ok' })
    state = chatReducer(state, { type: 'done', id: 'a1', usage: null, toolsCalled: [], retries: 0, metrics: { ttftMs: 1, tokensPerSec: null, totalMs: 1 } })

    state = chatReducer(state, send('u2', 'a2', 'second'))
    state = chatReducer(state, { type: 'error', id: 'a2', error: new Error('boom') })

    state = chatReducer(state, send('u3', 'a3', 'third'))
    state = chatReducer(state, { type: 'stop', id: 'a3' })

    state = chatReducer(state, send('u4', 'a4', 'fourth'))
    state = chatReducer(state, { type: 'delta', id: 'a4', text: 'ok again' })
    state = chatReducer(state, { type: 'done', id: 'a4', usage: null, toolsCalled: [], retries: 0, metrics: { ttftMs: 1, tokensPerSec: null, totalMs: 1 } })

    expect(turnsToHistory(state)).toEqual([
      { role: 'user', content: 'first' },
      { role: 'assistant', content: 'ok' },
      { role: 'user', content: 'fourth' },
      { role: 'assistant', content: 'ok again' },
    ])
  })
})
