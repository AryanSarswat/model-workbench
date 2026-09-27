import type { GpuInfo } from '../api/types'

const GPU_LABELS: Record<GpuInfo['kind'], string> = {
  apple_silicon: 'Apple Silicon',
  nvidia: 'NVIDIA',
  none: 'CPU only',
}

// "Apple Silicon", "CPU only", or the reported GPU name when known.
export function gpuLabel(gpu: GpuInfo): string {
  return gpu.kind === 'nvidia' && gpu.name ? gpu.name : GPU_LABELS[gpu.kind]
}
