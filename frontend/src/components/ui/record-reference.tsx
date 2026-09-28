export function RecordReference({ references }: { references: string[] }): JSX.Element {
  return <details className="mt-1 max-w-full text-meta text-ink-secondary">
    <summary className="cursor-pointer rounded-control py-1 text-accent focus-visible:outline focus-visible:outline-2">Record references</summary>
    <ul className="mt-1 space-y-1">{references.map(reference => <li key={reference}><code className="break-all">{reference}</code></li>)}</ul>
  </details>;
}
