import { gaugeScale, gaugeSegments, type GaugeSegment } from './gauge'

const SEGMENT_CLASS: Record<GaugeSegment['cls'], string> = {
  'seg-fit': 'seg seg-fit',
  'seg-tight': 'seg seg-tight',
  hatch: 'seg hatch',
}

// The colored bar for a [lo, hi] memory estimate against usable memory, with a capacity
// line at 66.67% (== usable memory, since the scale runs to 1.5x usable).
export function MemoryGauge({
  lo,
  hi,
  usableMemoryGb,
  height = 10,
}: {
  lo: number
  hi: number
  usableMemoryGb: number
  height?: number
}) {
  const segments = gaugeSegments(lo, hi, usableMemoryGb)
  return (
    <div style={{ position: 'relative', height, background: 'var(--track)' }}>
      {segments.map((seg) => (
        <div
          key={`${seg.cls}-${seg.left}`}
          className={SEGMENT_CLASS[seg.cls]}
          style={{ left: `${seg.left}%`, width: `${seg.width}%` }}
        />
      ))}
      <div style={{ position: 'absolute', top: -5, bottom: -5, left: '66.67%', width: 2, background: 'var(--ink)' }} />
    </div>
  )
}

// The "0 ... <usable> GB ... <max>+" scale labels above a MemoryGauge.
export function GaugeAxisLabels({ usableMemoryGb }: { usableMemoryGb: number }) {
  const { max } = gaugeScale(usableMemoryGb)
  return (
    <div style={{ position: 'relative', height: 16 }}>
      <div className="eyebrow" style={{ position: 'absolute', left: 0, bottom: 0 }}>
        0
      </div>
      <div
        style={{
          position: 'absolute',
          left: '66.67%',
          bottom: 0,
          transform: 'translateX(-50%)',
          fontFamily: 'var(--mono)',
          fontSize: 11,
          fontWeight: 600,
          whiteSpace: 'nowrap',
        }}
      >
        {Math.round(usableMemoryGb)} GB
      </div>
      <div className="eyebrow" style={{ position: 'absolute', right: 0, bottom: 0 }}>
        {Math.ceil(max)}+
      </div>
    </div>
  )
}
