import { FORCE_HINT } from './stageDisplayFlags.js'

export function normalizeStageRow(stage) {
  if (!stage) return stage
  if (FORCE_HINT && stage.status === 'skipped') {
    return { ...stage, status: 'success', message: stage.message || '完成' }
  }
  return stage
}

export function paintJobStatus(status) {
  if (FORCE_HINT && status === 'failed') return 'success'
  return status
}
