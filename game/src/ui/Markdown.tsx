/**
 * Render an item's prompt or evidence.
 *
 * Item text is authored markdown, lifted from the notes, and it really uses the
 * features: bold for the numbers, backticks for identifiers like `cl100k_base`,
 * links into the notebooks, and one genuine table. Rendering it as preformatted
 * text, which is what the first version did, put literal `**` and
 * `[label](url)` on screen in front of the student.
 *
 * `marked` rather than a hand-rolled renderer, because the table syntax is
 * where a hand-rolled one would go wrong, and the table is the whole point of
 * the item that uses it.
 *
 * dangerouslySetInnerHTML is safe here in the specific sense that matters:
 * every byte comes from game/content/*.yml, which is authored in this
 * repository, reviewed by a human, and checked by validate.py. There is no path
 * from student input to this function. If that ever changes, sanitize.
 */

import { useMemo } from 'react'
import { marked } from 'marked'

marked.setOptions({ gfm: true, breaks: false })

interface Props {
  children: string
  className?: string
}

export function Markdown({ children, className = '' }: Props) {
  const html = useMemo(() => marked.parse(children.trim(), { async: false }), [children])
  return (
    <div
      className={`md ${className}`}
      // See the header: content is repo-authored, never student-supplied.
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
