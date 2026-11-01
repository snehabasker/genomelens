import postmortem from '../../docs/postmortem.md?raw'

function esc(t: string) {
  return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function inline(t: string) {
  return esc(t).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[(.+?)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer noopener">$1</a>')
}

/** Tiny markdown renderer: headings, paragraphs, bullet/numbered lists, fenced code, tables. */
function render(src: string): string {
  const out: string[] = []
  const lines = src.split('\n')
  let i = 0
  while (i < lines.length) {
    const l = lines[i]
    if (l.startsWith('```')) {
      const buf: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) buf.push(lines[i++])
      i++
      out.push(`<pre>${esc(buf.join('\n'))}</pre>`)
    } else if (/^#{1,3} /.test(l)) {
      const n = l.match(/^#+/)![0].length
      out.push(`<h${n}>${inline(l.replace(/^#+ /, ''))}</h${n}>`); i++
    } else if (l.startsWith('|')) {
      const rows: string[][] = []
      while (i < lines.length && lines[i].startsWith('|')) {
        if (!/^\|[\s:|-]+\|?$/.test(lines[i])) rows.push(lines[i].split('|').slice(1, -1).map(c => c.trim()))
        i++
      }
      out.push('<table class="tbl"><thead><tr>' + rows[0].map(c => `<th>${inline(c)}</th>`).join('') + '</tr></thead><tbody>'
        + rows.slice(1).map(r => '<tr>' + r.map(c => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') + '</tbody></table>')
    } else if (/^(\s*[-*] |\d+\. )/.test(l)) {
      const ordered = /^\d+\. /.test(l)
      const items: string[] = []
      while (i < lines.length && /^(\s*[-*] |\d+\. )/.test(lines[i])) items.push(lines[i++].replace(/^(\s*[-*] |\d+\. )/, ''))
      const tag = ordered ? 'ol' : 'ul'
      out.push(`<${tag}>${items.map(x => `<li>${inline(x)}</li>`).join('')}</${tag}>`)
    } else if (l.trim() === '') {
      i++
    } else {
      const buf: string[] = []
      while (i < lines.length && lines[i].trim() !== '' && !/^(#|```|\||\s*[-*] |\d+\. )/.test(lines[i])) buf.push(lines[i++])
      out.push(`<p>${inline(buf.join(' '))}</p>`)
    }
  }
  return out.join('\n')
}

export default function PostMortem() {
  return <article className="card pad prose" dangerouslySetInnerHTML={{ __html: render(postmortem) }} />
}
