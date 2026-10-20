import { describe, expect, it } from 'vitest'
import { averageFace, faceDistance } from '@/lib/face'

describe('face templates', () => {
  it('measures the straight-line distance between two templates', () => {
    expect(faceDistance([0, 0, 0], [3, 4, 0])).toBe(5)
    expect(faceDistance([1, 2], [1, 2])).toBe(0)
  })

  it('averages several frames of the same face into one steadier template', () => {
    expect(averageFace([[0, 10], [2, 20], [4, 30]])).toEqual([2, 20])
  })

  it('keeps a lone frame as it is', () => {
    expect(averageFace([[1.5, -2]])).toEqual([1.5, -2])
  })
})
