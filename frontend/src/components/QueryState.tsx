export function QueryState({
  error,
  retry,
}: {
  error?: Error | null;
  retry: () => void;
}) {
  return error ? (
    <div className="notice error" role="alert">
      <h2>Unable to reach the local service</h2>
      <p>{error.message}. Check the application terminal, then try again.</p>
      <button onClick={retry}>Try again</button>
    </div>
  ) : (
    <p className="notice" role="status">
      Reading local configuration…
    </p>
  );
}
