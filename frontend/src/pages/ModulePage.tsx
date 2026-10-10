import { Navigate } from 'react-router-dom'

/** Fallback for an address that is not a routed module: send the user home. */
export function ModulePage() {
  return <Navigate to="/" replace />
}
