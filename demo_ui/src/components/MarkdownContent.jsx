import { createContext, useContext } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'

const InListContext = createContext(false)

// LlamaParse-parsed document text sometimes embeds raw HTML tables (with
// colspan/rowspan for merged cells) inline in otherwise-markdown content.
// defaultSchema already allows table elements but not these attributes.
const sanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    td: [...(defaultSchema.attributes?.td || []), 'colSpan', 'rowSpan', 'align'],
    th: [...(defaultSchema.attributes?.th || []), 'colSpan', 'rowSpan', 'align'],
  },
  // The inline citation markers below are rewritten into `citation:<idx>` links
  // (see preprocessCitations) — rehype-sanitize's default protocol allowlist
  // for `href` only permits http/https/irc/ircs/mailto/xmpp, so without this
  // it silently strips the href entirely and the click target is lost.
  protocols: {
    ...defaultSchema.protocols,
    href: [...(defaultSchema.protocols?.href || []), 'citation'],
  },
}

const components = {
  p: ({ children }) => {
    const inList = useContext(InListContext)
    return inList ? <>{children}</> : <p className="my-1 leading-relaxed">{children}</p>
  },
  ul: ({ children }) => <ul className="list-disc list-outside pl-4 my-1 space-y-0">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal list-outside pl-4 my-1 space-y-0">{children}</ol>,
  li: ({ children }) => (
    <InListContext.Provider value={true}>
      <li className="leading-relaxed">{children}</li>
    </InListContext.Provider>
  ),
  strong: ({ children }) => <strong className="font-semibold text-slate-900 dark:text-slate-100">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  code: ({ inline, children }) => inline
    ? <code className="bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200 rounded px-1 py-0.5 text-xs font-mono">{children}</code>
    : <code className="block bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-200 rounded-lg p-3 text-xs font-mono overflow-x-auto my-1">{children}</code>,
  pre: ({ children }) => <pre className="my-1">{children}</pre>,
  blockquote: ({ children }) => <blockquote className="border-l-2 border-brand-400 pl-3 text-slate-600 my-1">{children}</blockquote>,
  h1: ({ children }) => <h1 className="font-semibold text-base text-slate-900 dark:text-slate-100 my-1">{children}</h1>,
  h2: ({ children }) => <h2 className="font-semibold text-sm text-slate-900 dark:text-slate-100 my-1">{children}</h2>,
  h3: ({ children }) => <h3 className="font-semibold text-sm text-slate-900 dark:text-slate-100 my-0.5">{children}</h3>,
  table: ({ children }) => (
    <div className="my-2 max-w-full overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
      <table className="w-max min-w-full border-collapse text-xs whitespace-normal">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="min-w-28 max-w-72 bg-slate-50 dark:bg-slate-900 border-b border-r border-slate-200 dark:border-slate-700 px-3 py-2 text-left align-top font-semibold break-words last:border-r-0">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="min-w-28 max-w-72 border-b border-r border-slate-200 dark:border-slate-700 px-3 py-2 align-top break-words last:border-r-0">
      {children}
    </td>
  ),
}

// Matches the citation format assistant replies actually use in practice:
// "[<filename>, p.<page>]" (the system prompt describes this as "[doc:<filename>,
// p.<page>]", but the model consistently omits the "doc:" prefix — matching
// real output here, not the prompt's literal wording). Deliberately does NOT
// match bracketed text without a ", p.<N>]" suffix, e.g. the separate
// "[Background Gap Analysis Reference]" marker used for non-document context —
// that one has no backing chunk to link to, so it's left as plain text.
const CITATION_RE = /\[(?:doc:\s*)?([^,\]]+?)\s*,\s*p\.\s*(\d+)\s*\]/gi
const ANALYSIS_CITATION_RE = /\[analysis:([^,\]]+),\s*clause\s+([^\]]+)\]/gi
const SOURCE_CITATION_RE = /\[source:([^\]]+)\]/gi

function citationLabel(citation) {
  if (citation?.display_label) return citation.display_label
  if (citation?.type === 'analysis') return `Clause ${citation.clause_id} · ${citation.decision}`
  return `${citation?.filename || 'Document'} · p.${citation?.page ?? '?'}`
}

function citationMarkdown(citation, idx) {
  const label = citationLabel(citation).replace(/([\\\[\]])/g, '\\$1')
  return `[${label}](citation:${idx})`
}

// Rewrites each citation marker into a placeholder markdown link keyed by the
// citation's index in `citations` (rather than embedding the raw filename in
// the link text/href, which could contain characters that break markdown
// link syntax). The custom `a` renderer below turns these into clickable
// green badges instead of real links.
function preprocessCitations(content, citations) {
  if (!citations?.length) return content
  const withSources = content.replace(SOURCE_CITATION_RE, (match, sourceKey) => {
    const idx = citations.findIndex(c => String(c.source_key) === sourceKey.trim())
    return idx >= 0 ? citationMarkdown(citations[idx], idx) : match
  })
  const withAnalysis = withSources.replace(ANALYSIS_CITATION_RE, (match, analysisId, clauseId) => {
    const idx = citations.findIndex(c =>
      c.type === 'analysis' &&
      String(c.analysis_id) === analysisId.trim() &&
      String(c.clause_id) === clauseId.trim()
    )
    return idx >= 0 ? citationMarkdown(citations[idx], idx) : match
  })
  return withAnalysis.replace(CITATION_RE, (match, filename, page) => {
    const idx = citations.findIndex(c =>
      c.filename?.trim().toLowerCase() === filename.trim().toLowerCase() &&
      String(c.page) === String(page)
    )
    return idx >= 0 ? citationMarkdown(citations[idx], idx) : match
  })
}

function CitationLink({ href, citations, onCitationClick }) {
  const idx = Number(href.slice('citation:'.length))
  const citation = citations?.[idx]
  return (
    <button
      type="button"
      onClick={() => citation && onCitationClick?.(citation)}
      disabled={!citation}
      title={citation ? (citation.type === 'analysis'
        ? `Analysis ${citation.analysis_id} — clause ${citation.clause_id}`
        : `${citation.filename} — p.${citation.page}`) : 'Citation unavailable'}
      className={`inline-flex max-w-full items-center gap-1 mx-0.5 -translate-y-px px-2 py-0.5 rounded-md text-[11px] font-semibold align-middle transition-all ${
        citation
          ? 'bg-emerald-50 text-emerald-800 border border-emerald-200 hover:bg-emerald-100 hover:border-emerald-300 hover:shadow-sm cursor-pointer'
          : 'bg-slate-100 text-slate-400 border border-slate-200 cursor-default'
      }`}
    >
      <span className="truncate">{citation ? citationLabel(citation) : '?'}</span>
    </button>
  )
}

export default function MarkdownContent({ content, className, citations, onCitationClick }) {
  const processed = preprocessCitations(content, citations)
  const componentsWithCitations = {
    ...components,
    a: ({ href, children }) => (
      href?.startsWith('citation:')
        ? <CitationLink href={href} citations={citations} onCitationClick={onCitationClick} />
        : <a href={href} className="text-brand-600 hover:underline" target="_blank" rel="noopener noreferrer">{children}</a>
    ),
  }
  const body = (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema]]}
      components={componentsWithCitations}
    >
      {processed}
    </ReactMarkdown>
  )
  return (
    <div className={`min-w-0 max-w-full whitespace-normal ${className || ''}`}>
      {body}
    </div>
  )
}
