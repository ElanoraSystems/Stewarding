import { useEffect, useRef, useState } from 'react'
import { averageFace, faceDistance, loadFaceModels } from '@/lib/face'
import { cn } from '@/lib/utils'

export type FaceResult = { ok: true; message?: string } | { ok: false; message: string }

interface FaceCaptureProps {
  /** Called once a steady face is seen, with its template; say whether it worked so the box can show it. */
  onCapture: (descriptor: number[]) => Promise<FaceResult>
}

const STEADY_FRAMES = 3
const STEADY_DISTANCE = 0.3
const FRAME_MS = 300
const RETRY_MS = 2500

type Phase = 'starting' | 'looking' | 'checking' | 'ok' | 'failed' | 'blocked'

/**
 * Shows the front camera with a box that follows the face. When the same face is seen on a few frames in a row,
 * its template is passed to onCapture. The camera and the model both run in this browser; only the template leaves it.
 */
export function FaceCapture({ onCapture }: FaceCaptureProps) {
  const video = useRef<HTMLVideoElement>(null)
  const overlay = useRef<HTMLCanvasElement>(null)
  const [phase, setPhase] = useState<Phase>('starting')
  const [message, setMessage] = useState('Starting the camera')
  const capture = useRef(onCapture)
  useEffect(() => {
    capture.current = onCapture
  })

  useEffect(() => {
    let stopped = false
    let stream: MediaStream | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let recent: Float32Array[] = []

    const show = (next: Phase, text: string) => {
      if (stopped) return
      setPhase(next)
      setMessage(text)
    }

    async function run() {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error('camera-unavailable')
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }, audio: false })
        if (stopped || !video.current) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        video.current.srcObject = stream
        await video.current.play()
        show('starting', 'Loading the face model')
        const faceapi = await loadFaceModels()
        const options = new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 })
        show('looking', 'Look at the camera')

        const tick = async () => {
          if (stopped || !video.current) return
          const found = await faceapi.detectSingleFace(video.current, options).withFaceLandmarks(true).withFaceDescriptor()
          const canvas = overlay.current
          const context = canvas?.getContext('2d')
          if (canvas && context && video.current) {
            canvas.width = video.current.videoWidth
            canvas.height = video.current.videoHeight
            context.clearRect(0, 0, canvas.width, canvas.height)
            if (found) {
              const { x, y, width, height } = found.detection.box
              context.lineWidth = 4
              context.strokeStyle = recent.length >= STEADY_FRAMES - 1 ? '#16a34a' : '#facc15'
              context.strokeRect(x, y, width, height)
            }
          }
          if (!found) {
            recent = []
            show('looking', 'Look at the camera')
          } else {
            const last = recent[recent.length - 1]
            recent = last && faceDistance(last, found.descriptor) > STEADY_DISTANCE ? [found.descriptor] : [...recent, found.descriptor]
            if (recent.length >= STEADY_FRAMES) {
              show('checking', 'Checking your face')
              const result = await capture.current(averageFace(recent))
              recent = []
              if (result.ok) {
                show('ok', result.message ?? 'Match found!')
                return
              }
              show('failed', result.message)
              timer = setTimeout(tick, RETRY_MS)
              return
            }
            show('looking', 'Hold still')
          }
          timer = setTimeout(tick, FRAME_MS)
        }
        void tick()
      } catch (err) {
        const denied = err instanceof DOMException && err.name === 'NotAllowedError'
        show('blocked', denied ? 'Allow camera access in your browser, then open this again'
          : err instanceof Error && err.message === 'camera-unavailable' ? 'Camera access needs a secure (https) page'
            : 'The camera or the face model could not start')
      }
    }

    void run()
    return () => {
      stopped = true
      clearTimeout(timer)
      stream?.getTracks().forEach((t) => t.stop())
    }
  }, [])

  return (
    <div className="space-y-3">
      <div className="relative mx-auto aspect-[4/3] w-full max-w-sm overflow-hidden rounded-xl bg-black">
        <video ref={video} muted playsInline className="h-full w-full -scale-x-100 object-cover" />
        <canvas ref={overlay} aria-hidden className="absolute inset-0 h-full w-full -scale-x-100 object-cover" />
      </div>
      <p role="status" className={cn('text-center text-sm font-medium', phase === 'ok' && 'text-ok', (phase === 'failed' || phase === 'blocked') && 'text-danger')}>{message}</p>
    </div>
  )
}
