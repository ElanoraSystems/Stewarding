import type * as FaceApi from '@vladmandic/face-api'

/** Where the model weights are served from; they are copied from the face-api package into public/models. */
const MODEL_URL = '/models'

let loading: Promise<typeof FaceApi> | null = null

/** Loads the face library and the three small models once, only when a camera screen needs them. */
export function loadFaceModels(): Promise<typeof FaceApi> {
  loading ??= import('@vladmandic/face-api').then(async (faceapi) => {
    await Promise.all([
      faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
      faceapi.nets.faceLandmark68TinyNet.loadFromUri(MODEL_URL),
      faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
    ])
    return faceapi
  })
  loading.catch(() => { loading = null })
  return loading
}

/** Straight-line distance between two face templates; smaller means more alike. */
export function faceDistance(a: ArrayLike<number>, b: ArrayLike<number>): number {
  let sum = 0
  for (let i = 0; i < a.length; i++) sum += (a[i] - b[i]) ** 2
  return Math.sqrt(sum)
}

/** The mean of several templates of the same face, which is steadier than a single frame. */
export function averageFace(faces: ArrayLike<number>[]): number[] {
  return Array.from(faces[0], (_, i) => faces.reduce((sum, f) => sum + f[i], 0) / faces.length)
}
