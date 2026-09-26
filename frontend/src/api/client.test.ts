import { describe, expect, it, vi } from 'vitest'
import { ApiError, apiGet, apiSend } from './client'

function stubFetch(response: Response) {
  const fetchMock = vi.fn(async () => response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('api client', () => {
  it('turns the backend error shape into an ApiError', async () => {
    stubFetch(
      Response.json(
        {
          error: {
            code: 'invalid_gguf_filename',
            message: "'x.gguf' is not a GGUF file in Qwen/Qwen3-14B.",
            details: { available: ['a.gguf'] },
          },
        },
        { status: 400 },
      ),
    )

    const error = await apiSend('POST', '/models/Qwen/Qwen3-14B/download', { filename: 'x.gguf' }).catch(
      (e: unknown) => e,
    )

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 400,
      code: 'invalid_gguf_filename',
      message: "'x.gguf' is not a GGUF file in Qwen/Qwen3-14B.",
      details: { available: ['a.gguf'] },
    })
  })

  it('reports FastAPI validation errors and non-JSON failures readably', async () => {
    stubFetch(Response.json({ detail: [{ loc: ['body', 'model_id'], msg: 'Field required' }] }, { status: 422 }))
    await expect(apiGet('/evals/runs')).rejects.toMatchObject({
      code: 'validation_error',
      message: 'body.model_id: Field required',
    })

    stubFetch(new Response('Bad Gateway', { status: 502 }))
    await expect(apiGet('/tools')).rejects.toMatchObject({ status: 502, message: 'Request failed: Bad Gateway' })
  })

  it('prefixes /api and returns undefined for 204', async () => {
    const fetchMock = stubFetch(new Response(null, { status: 204 }))

    await expect(apiSend('DELETE', '/chat/sessions/3')).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith('/api/chat/sessions/3', expect.objectContaining({ method: 'DELETE' }))
  })
})
