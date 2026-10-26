import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AdminLesson } from '@/lib/training'
import { ToastProvider } from '@/lib/toast'
import { SlideVideoEditor } from '@/pages/training/SlideVideoEditor'

const mocks = vi.hoisted(() => ({ api: vi.fn(), typed: false, status: null as string | null, slides: [] as unknown[] }))
vi.mock('@/lib/api', () => ({ api: mocks.api, tokenStore: { get: () => 'token' } }))
vi.mock('@/lib/useApi', () => ({
  useApi: (path: string) => {
    if (path === '/training/voice') return { data: { typed: mocks.typed }, reload: vi.fn() }
    const lesson: AdminLesson = {
      id: 7, position: 0, title: 'Fridge temperatures', kind: 'video', body: null, external_url: null, media: null, questions: [],
      slides: mocks.slides as AdminLesson['slides'], video: { status: mocks.status as AdminLesson['video']['status'], error: null },
    }
    return { data: { id: 1, title: 'Cold Storage Safety', lesson_list: [lesson] }, reload: vi.fn() }
  },
}))

const open = () => render(<ToastProvider><SlideVideoEditor courseId={1} lessonId={7} onClose={vi.fn()} onChanged={vi.fn()} /></ToastProvider>)

describe('SlideVideoEditor', () => {
  beforeEach(() => {
    mocks.api.mockReset()
    mocks.typed = false
    mocks.status = null
    mocks.slides = []
  })

  it('starts with one slide named after the lesson, and says when typed voice-over is not available', () => {
    open()
    expect((screen.getByLabelText('Slide title') as HTMLInputElement).value).toBe('Fridge temperatures')
    expect((screen.getByLabelText(/Type what is said/) as HTMLInputElement).disabled).toBe(true)
    expect(screen.getByText(/Not set up on this server yet/)).toBeTruthy()
    expect((screen.getByLabelText(/Upload a recording/) as HTMLInputElement).disabled).toBe(false)
  })

  it('offers typed voice-over once the server has a voice', () => {
    mocks.typed = true
    open()
    expect((screen.getByLabelText(/Type what is said/) as HTMLInputElement).disabled).toBe(false)
    expect(screen.queryByText(/Not set up on this server yet/)).toBeNull()
  })

  it('saves the slides with the points split one per line, then makes the video', async () => {
    mocks.api.mockResolvedValue({ slides: [{ id: 'abc123abc123', title: 'Fridge temperatures', bullets: ['Below 5', 'Log it'], narration: null, voice: 'none', seconds: 6, image: null, audio: null }] })
    open()
    fireEvent.change(screen.getByLabelText('Points (one per line)'), { target: { value: 'Below 5\n\n  Log it  ' } })
    fireEvent.click(screen.getByRole('button', { name: /Make the video/ }))
    await waitFor(() => expect(mocks.api).toHaveBeenCalledWith('/training/lessons/7/render', { method: 'POST' }))
    expect(mocks.api).toHaveBeenNthCalledWith(1, '/training/lessons/7/slides', {
      method: 'PUT', body: { slides: [{ id: null, title: 'Fridge temperatures', bullets: ['Below 5', 'Log it'], narration: null, voice: 'none', seconds: 6 }] },
    })
  })

  it('adds slides and can choose a recording for one of them', () => {
    open()
    fireEvent.click(screen.getByRole('button', { name: /Add slide/ }))
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect((screen.getByLabelText('Slide title') as HTMLInputElement).value).toBe('')
    fireEvent.click(screen.getByLabelText(/Upload a recording/))
    expect(screen.getByRole('button', { name: /Choose a recording/ })).toBeTruthy()
  })

  it('shows that the video is being made and holds the form still until it is done', () => {
    mocks.status = 'rendering'
    mocks.slides = [{ id: 'abc123abc123', title: 'One', bullets: [], narration: null, voice: 'none', seconds: 6, image: null, audio: null }]
    open()
    expect(screen.getByText(/Being made/)).toBeTruthy()
    expect((screen.getByRole('button', { name: /Make the video/ }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByLabelText('Slide title') as HTMLInputElement).closest('fieldset')?.disabled).toBe(true)
  })
})
