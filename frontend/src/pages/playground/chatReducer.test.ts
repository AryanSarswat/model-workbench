import { describe, expect, it } from 'vitest'
import { chatReducer } from './chatReducer'

describe('chatReducer', () => {
  it('appends a user turn and a streaming assistant placeholder on send', () => {
    const state = chatReducer([], { type: 'send', userId: 'u1', assistantId: 'a1', content: 'hi', hadSchema: false })

    expect(state).toHaveLength(2)
    expect(state[0]).toMatchObject({ id: 'u1', role: 'user', content: 'hi', streaming: false })
    expect(state[1]).toMatchObject({ id: 'a1', role: 'assistant', content: '', streaming: true, hadSchema: false })
  })

  it('accumulates deltas onto the streaming assistant turn only', () => {
    let state = chatReducer([], { type: 'send', userId: 'u1', assistantId: 'a1', content: 'hi', hadSchema: false })
    state = chatReducer(state, { type: 'delta', id: 'a1', text: 'Hel' })
    state = chatReducer(state, { type: 'delta', id: 'a1', text: 'lo' })

    expect(state[1].content).toBe('Hello')
    expect(state[0].content).toBe('hi') // the user turn is untouched
  })

  it('done attaches usage, tools called, retries and metrics, and stops streaming', () => {
    let state = chatReducer([], { type: 'send', userId: 'u1', assistantId: 'a1', content: 'hi', hadSchema: false })
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
    let state = chatReducer([], { type: 'send', userId: 'u1', assistantId: 'a1', content: 'hi', hadSchema: false })
    const error = new Error('boom')
    state = chatReducer(state, { type: 'error', id: 'a1', error })

    expect(state[1]).toMatchObject({ streaming: false, error })
  })

  it('reset clears the transcript for New chat', () => {
    let state = chatReducer([], { type: 'send', userId: 'u1', assistantId: 'a1', content: 'hi', hadSchema: false })
    state = chatReducer(state, { type: 'reset' })

    expect(state).toEqual([])
  })
})
