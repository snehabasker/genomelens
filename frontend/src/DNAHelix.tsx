import { useEffect, useRef, useState, useMemo } from 'react'
import type { Mutation } from './types'

const BASE_COLORS: Record<string, string> = { A: '#3b82f6', T: '#ef4444', G: '#10b981', C: '#f59e0b', N: '#4b5563' }
const COMPLEMENT: Record<string, string> = { A: 'T', T: 'A', G: 'C', C: 'G', N: 'N' }

function generatePlaceholderSeq(len = 40) {
  const bases = ['A', 'T', 'G', 'C']
  return Array.from({ length: len }, () => bases[Math.floor(Math.random() * 4)]).join('')
}

interface Props {
  sequence?: string
  variantPosition?: number | null
  mutation?: Mutation | null
  isScanning?: boolean
}

interface HelixNode {
  base: string
  comp: string
  y: number
  x1: number
  x2: number
  isVariant: boolean
  i: number
}

export default function DNAHelix({ sequence = '', variantPosition = null, mutation = null, isScanning = false }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const offsetRef = useRef(0)
  const [, setTick] = useState(0)

  // Animate scanning scroll
  useEffect(() => {
    if (!isScanning && !mutation) return
    const id = setInterval(() => {
      offsetRef.current = (offsetRef.current + 0.5) % (2 * Math.PI)
      setTick(t => t + 1)
    }, 50)
    return () => clearInterval(id)
  }, [isScanning, mutation])

  const placeholder = useMemo(() => generatePlaceholderSeq(40), [])
  const displaySeq = sequence.length >= 20 ? sequence : placeholder
  const visibleCount = Math.min(displaySeq.length, 28)
  const W = 220
  const H = 520
  const cx = W / 2
  const amplitude = 60
  const baseSpacing = H / visibleCount

  const nodes: HelixNode[] = []
  for (let i = 0; i < visibleCount; i++) {
    const base = displaySeq[i] || 'N'
    const comp = COMPLEMENT[base] || 'N'
    const y = i * baseSpacing + baseSpacing / 2
    const phase = (i / visibleCount) * 2 * Math.PI * 2 + offsetRef.current
    const x1 = cx + amplitude * Math.sin(phase)
    const x2 = cx - amplitude * Math.sin(phase)
    const isVariant = variantPosition !== null && i === variantPosition
    nodes.push({ base, comp, y, x1, x2, isVariant, i })
  }

  return (
    <div className="helix-container">
      <svg ref={svgRef} width={W} height={H} className="dna-svg">
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="mutGlow">
            <feGaussianBlur stdDeviation="5" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Backbone lines */}
        {nodes.map((n, idx) => {
          if (idx === 0) return null
          const prev = nodes[idx - 1]
          return (
            <g key={`backbone-${idx}`}>
              <line x1={prev.x1} y1={prev.y} x2={n.x1} y2={n.y}
                stroke="#1e3a5f" strokeWidth="1.5" opacity="0.6" />
              <line x1={prev.x2} y1={prev.y} x2={n.x2} y2={n.y}
                stroke="#1e3a5f" strokeWidth="1.5" opacity="0.6" />
            </g>
          )
        })}

        {/* Base pairs */}
        {nodes.map((n) => {
          const color1 = n.isVariant ? '#ff0066' : (BASE_COLORS[n.base] || '#4b5563')
          const color2 = n.isVariant ? '#ff0066' : (BASE_COLORS[n.comp] || '#4b5563')
          const r = n.isVariant ? 7 : 5
          const filter = n.isVariant ? 'url(#mutGlow)' : 'url(#glow)'

          return (
            <g key={`pair-${n.i}`}>
              {/* Connector bar */}
              <line x1={n.x1} y1={n.y} x2={n.x2} y2={n.y}
                stroke={n.isVariant ? '#ff006640' : '#1e3a5f'} strokeWidth="1" />

              {/* Left node */}
              <circle cx={n.x1} cy={n.y} r={r} fill={color1} filter={filter}
                className={n.isVariant ? 'mutation-pulse' : ''} />
              <text x={n.x1} y={n.y + 1} textAnchor="middle" dominantBaseline="middle"
                fontSize="6" fill="white" fontFamily="JetBrains Mono" fontWeight="600">
                {n.isVariant ? '!' : n.base}
              </text>

              {/* Right node */}
              <circle cx={n.x2} cy={n.y} r={r} fill={color2} filter={filter}
                className={n.isVariant ? 'mutation-pulse' : ''} />
              <text x={n.x2} y={n.y + 1} textAnchor="middle" dominantBaseline="middle"
                fontSize="6" fill="white" fontFamily="JetBrains Mono" fontWeight="600">
                {n.isVariant ? '!' : n.comp}
              </text>
            </g>
          )
        })}

        {/* Scanning beam */}
        {isScanning && (
          <rect x={0} y={0} width={W} height={4} fill="url(#scanGrad)" className="scan-beam">
            <animateTransform attributeName="transform" type="translate"
              from={`0 0`} to={`0 ${H}`} dur="2s" repeatCount="indefinite" />
          </rect>
        )}
      </svg>

      {/* Legend */}
      <div className="helix-legend">
        {Object.entries(BASE_COLORS).filter(([b]) => b !== 'N').map(([base, color]) => (
          <span key={base} className="legend-item">
            <span className="legend-dot" style={{ background: color }} />
            {base}
          </span>
        ))}
        {mutation && (
          <span className="legend-item mutation-legend">
            <span className="legend-dot" style={{ background: '#ff0066' }} />
            Mutation
          </span>
        )}
      </div>

      {/* Mutation badge */}
      {mutation && (
        <div className="mutation-badge">
          <span className="mut-type">{mutation.type}</span>
          <span className="mut-change">
            {mutation.ref || '?'} → {mutation.alt || '?'}
          </span>
        </div>
      )}
    </div>
  )
}
