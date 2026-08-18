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
  strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  code: ({ inline, children }) => inline
    ? <code className="bg-slate-100 text-slate-700 rounded px-1 py-0.5 text-xs font-mono">{children}</code>
    : <code className="block bg-slate-100 text-slate-700 rounded-lg p-3 text-xs font-mono overflow-x-auto my-1">{children}</code>,
  pre: ({ children }) => <pre className="my-1">{children}</pre>,
  blockquote: ({ children }) => <blockquote className="border-l-2 border-brand-400 pl-3 text-slate-600 my-1">{children}</blockquote>,
  h1: ({ children }) => <h1 className="font-semibold text-base text-slate-900 my-1">{children}</h1>,
  h2: ({ children }) => <h2 className="font-semibold text-sm text-slate-900 my-1">{children}</h2>,
  h3: ({ children }) => <h3 className="font-semibold text-sm text-slate-900 my-0.5">{children}</h3>,
  a: ({ href, children }) => <a href={href} className="text-brand-600 hover:underline" target="_blank" rel="noopener noreferrer">{children}</a>,
  table: ({ children }) => <table className="text-xs border-collapse my-1 w-full">{children}</table>,
  th: ({ children }) => <th className="bg-slate-50 border border-slate-200 px-2 py-1 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border border-slate-200 px-2 py-1">{children}</td>,
}

export default function MarkdownContent({ content, className }) {
  const body = (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema]]}
      components={components}
    >
      {content}
    </ReactMarkdown>
  )
  return className ? <div className={className}>{body}</div> : body
}
