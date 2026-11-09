/** The single error shape {error: {code, message}} (D-20), or a client-side error with the same fields. */
export function ErrorBox({ code, message }: { code: string; message: string }) {
  return (
    <div role="alert">
      <strong>{code}</strong>: {message}
    </div>
  );
}
