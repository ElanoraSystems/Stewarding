import jsQR from 'jsqr'
import { useEffect, useRef, useState } from 'react'
import { Modal } from '@/components/ui/modal'

interface Detector {
  detect: (source: CanvasImageSource) => Promise<{ rawValue: string }[]>
}

interface Props {
  open: boolean
  onClose: () => void
  onScan: (code: string) => void
}

/** The camera view; mounted only while the dialog is open, so every scan starts fresh and the camera is released on close. */
function Camera({ onScan }: { onScan: (code: string) => void }) {
  const video = useRef<HTMLVideoElement>(null)
  const found = useRef(onScan)
  const [message, setMessage] = useState('Starting the camera')
  useEffect(() => {
    found.current = onScan
  })

  useEffect(() => {
    let stopped = false
    let stream: MediaStream | null = null
    let timer: ReturnType<typeof setTimeout> | undefined

    async function run() {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error('camera-unavailable')
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
        if (stopped || !video.current) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        video.current.srcObject = stream
        await video.current.play()
        setMessage('Point the camera at the QR code on the label')
        const Native = (window as unknown as { BarcodeDetector?: new (options: { formats: string[] }) => Detector }).BarcodeDetector
        const detector = Native ? new Native({ formats: ['qr_code'] }) : null
        const canvas = document.createElement('canvas')

        const look = async () => {
          if (stopped || !video.current) return
          let text: string | null = null
          if (detector) {
            text = (await detector.detect(video.current).catch(() => []))[0]?.rawValue ?? null
          } else if (video.current.videoWidth) {
            canvas.width = video.current.videoWidth
            canvas.height = video.current.videoHeight
            const context = canvas.getContext('2d', { willReadFrequently: true })
            context?.drawImage(video.current, 0, 0)
            const image = context?.getImageData(0, 0, canvas.width, canvas.height)
            text = image ? jsQR(image.data, image.width, image.height)?.data ?? null : null
          }
          if (text) {
            found.current(text.trim())
            return
          }
          timer = setTimeout(look, 250)
        }
        void look()
      } catch (err) {
        const denied = err instanceof DOMException && err.name === 'NotAllowedError'
        setMessage(denied ? 'Allow camera access in your browser, or type the lot code instead'
          : err instanceof Error && err.message === 'camera-unavailable' ? 'Camera access needs a secure (https) page. Type the lot code instead'
            : 'The camera could not start. Type the lot code instead')
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
    <>
      <div className="relative mx-auto aspect-[4/3] w-full max-w-sm overflow-hidden rounded-xl bg-black">
        <video ref={video} muted playsInline className="h-full w-full object-cover" />
        <span aria-hidden className="absolute inset-8 rounded-lg border-2 border-white/70" />
      </div>
      <p role="status" className="mt-3 text-center text-sm font-medium">{message}</p>
    </>
  )
}

/** Reads a QR label with the back camera: the browser's own detector where there is one, otherwise a small decoder. */
export function LotScanner({ open, onClose, onScan }: Props) {
  return (
    <Modal open={open} title="Scan a lot label" onClose={onClose}>
      {open && <Camera onScan={onScan} />}
    </Modal>
  )
}
