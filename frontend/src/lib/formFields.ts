export type FieldType = 'number' | 'yes_no' | 'text' | 'choice' | 'date' | 'time' | 'signature' | 'image'

export interface FieldSpec {
  title: string
  type: FieldType
  unit: string
  min: string
  max: string
  warnMin: string  // an amber warning level: a number at or below this still passes
  warnMax: string  // a number at or above this still passes
  options: string
  fail: string[]
  maxLength: string
  reference: boolean
  traceLots: boolean
  required: boolean
}

export const FIELD_TYPES: { value: FieldType; label: string }[] = [
  { value: 'number', label: 'Number' },
  { value: 'yes_no', label: 'Yes or no' },
  { value: 'text', label: 'Short text' },
  { value: 'date', label: 'Date picker' },
  { value: 'time', label: 'Time picker' },
  { value: 'signature', label: 'Signature box' },
  { value: 'image', label: 'Image upload' },
  { value: 'choice', label: 'Dropdown (choose one)' },
]

export const blankField = (): FieldSpec => ({ title: '', type: 'number', unit: '', min: '', max: '', warnMin: '', warnMax: '', options: '', fail: [], maxLength: '200', reference: false, traceLots: false, required: true })

export const optionList = (text: string): string[] => [...new Set(text.split('\n').map((o) => o.trim().replace(/\s+/g, ' ')).filter(Boolean))]

/** What is wrong with a field, in words, or null when it can be saved. */
export function fieldProblem(f: FieldSpec): string | null {
  if (f.title.trim().length < 2) return 'Give every field a title.'
  if (f.type === 'number') {
    if (f.min === '' && f.max === '') return `${f.title}: a number needs a minimum or a maximum. For anything without limits use Short text.`
    if (f.min !== '' && f.max !== '' && Number(f.min) > Number(f.max)) return `${f.title}: the minimum is above the maximum.`
    if (f.warnMax !== '' && ((f.max !== '' && Number(f.warnMax) > Number(f.max)) || (f.min !== '' && Number(f.warnMax) < Number(f.min)))) return `${f.title}: the warning level above must sit within the limits.`
    if (f.warnMin !== '' && ((f.min !== '' && Number(f.warnMin) < Number(f.min)) || (f.max !== '' && Number(f.warnMin) > Number(f.max)))) return `${f.title}: the warning level below must sit within the limits.`
  }
  if (f.type === 'choice') {
    const options = optionList(f.options)
    if (options.length < 2) return `${f.title}: list at least two answers, one per line.`
    if (options.length > 20) return `${f.title}: at most 20 answers.`
  }
  if (f.type === 'text' && (Number(f.maxLength) < 1 || Number(f.maxLength) > 500)) return `${f.title}: the maximum length is between 1 and 500.`
  return null
}

export function fieldPayload(f: FieldSpec) {
  const options = optionList(f.options)
  return {
    title: f.title.trim(), value_type: f.type, require_reference: f.reference, trace_lots: f.traceLots, required: f.required,
    unit: f.type === 'number' ? f.unit.trim() || null : null,
    min_value: f.type === 'number' && f.min !== '' ? Number(f.min) : null,
    max_value: f.type === 'number' && f.max !== '' ? Number(f.max) : null,
    warn_min: f.type === 'number' && f.warnMin !== '' ? Number(f.warnMin) : null,
    warn_max: f.type === 'number' && f.warnMax !== '' ? Number(f.warnMax) : null,
    options: f.type === 'choice' ? options : null,
    fail_options: f.type === 'choice' ? f.fail.filter((o) => options.includes(o)) : null,
    max_length: f.type === 'text' ? Number(f.maxLength) : null,
  }
}

/** Ready-made forms to start from in the form builder; the person still chooses where it is used and how many times a day. */
export const FORM_PRESETS: { key: string; label: string; name: string; kind: string; time: string; fields: FieldSpec[] }[] = [
  {
    key: 'tpm', label: 'Frying oil (TPM)', name: 'Frying oil (TPM)', kind: 'Frying oil', time: '15:00',
    fields: [
      { ...blankField(), title: 'TPM reading', unit: '%', min: '0', max: '25', warnMax: '20' },
      { ...blankField(), title: 'Oil temperature', unit: '°C', min: '160', max: '190' },
      { ...blankField(), title: 'Oil look and smell', type: 'choice', options: 'Normal\nDark\nFoaming\nSmoking\nOff smell', fail: ['Foaming', 'Smoking', 'Off smell'], required: false },
    ],
  },
]
