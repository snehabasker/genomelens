import { useEffect, useState } from 'react'
import AttackLab from './AttackLab'
import EvalDashboard from './EvalDashboard'
import Lab from './Lab'
import PostMortem from './PostMortem'
import { useRun } from './useRun'
import type { RawEvent, ServerConfig } from './types'

type Tab = 'lab' | 'attack' | 'eval' | 'postmortem'
const TABS: [Tab, string][] = [['lab', 'Lab'], ['attack', 'Try to break it'], ['eval', 'Evaluation'], ['postmortem', 'Post-mortem']]

export default function App() {
  const fromHash = (): Tab => {
    const h = window.location.hash.replace('#', '').split('&')[0] as Tab
    return (['lab', 'attack', 'eval', 'postmortem'] as Tab[]).includes(h) ? h : 'lab'
  }
  const [tab, setTab] = useState<Tab>(fromHash)
  const [config, setConfig] = useState<ServerConfig | null>(null)
  const main = useRun()
  const prot = useRun()
  const orig = useRun()

  useEffect(() => {
    fetch('/api/config').then(r => r.json()).then(setConfig).catch(() => {})
  }, [])

  const provider: 'cloud' | 'local' = config?.local_available ? 'local' : 'cloud'
  const replay = (events: RawEvent[]) => { main.load(events); setTab('lab') }

  return (
    <div className="app">
      <header className="top">
        <div className="brand"><span className="logo">⬡</span><b>GENOME LENS</b>
          <span className="tag-line">multi-agent variant intelligence, with the receipts</span></div>
        <nav role="tablist">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'on' : ''} onClick={() => { setTab(id); history.replaceState(null, '', `#${id}`) }}>{label}</button>
          ))}
        </nav>
        <div className="status">
          <span className={`dot ws-${main.wsStatus}`} />{main.wsStatus}
          {config && <span className={`budget ${config.budget.exhausted ? 'out' : ''}`}
            title="Daily AI spend cap for the public demo">AI budget ${config.budget.spent_usd.toFixed(2)} / ${config.budget.daily_usd.toFixed(2)}</span>}
        </div>
      </header>
      {/* all tabs stay mounted so a running analysis is never lost when switching */}
      <div hidden={tab !== 'lab'}><Lab run={main} config={config} /></div>
      <div hidden={tab !== 'attack'}><AttackLab config={config} protectedRun={prot} originalRun={orig} provider={provider} /></div>
      <div hidden={tab !== 'eval'}>{tab === 'eval' && <EvalDashboard onReplay={replay} />}</div>
      <div hidden={tab !== 'postmortem'}>{tab === 'postmortem' && <PostMortem />}</div>
    </div>
  )
}
