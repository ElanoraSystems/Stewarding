export interface Position {
  latitude: number
  longitude: number
  accuracy: number
}

/** The device position, or an error saying what to do when location access is refused or unavailable. */
export function currentPosition(): Promise<Position> {
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject(new Error('This device cannot share its location, so it cannot check in here'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy: p.coords.accuracy }),
      (e) => reject(new Error(e.code === e.PERMISSION_DENIED ? 'Allow location access in your browser to check in or out at this location' : 'Your location could not be found. Try again outdoors or with Wi-Fi on')),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    )
  })
}
