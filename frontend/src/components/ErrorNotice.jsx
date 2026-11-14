const HINTS = {
  network_error: 'Check that the API server is running, then reload this page.',
  access_denied: 'Enter the access password you were given.',
}

export default function ErrorNotice({ error, hint, title = 'Something went wrong' }) {
  if (!error) return null
  const advice = hint ?? HINTS[error.code] ?? 'Reload the page. If it keeps happening, go back to your papers and try again.'
  return (
    <div role="alert" className="notice" data-tone="bad">
      <p className="notice-title">{title}</p>
      <p>{error.message}</p>
      <p className="muted">{advice}</p>
    </div>
  )
}
