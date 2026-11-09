import { createRoot } from "react-dom/client";

import App from "./App";

// StrictMode is off: its double-invoked effects would send each request twice in development (the first is
// aborted by useAsync). What this gives up is StrictMode's development check for effects without a cleanup.
createRoot(document.getElementById("root")!).render(<App />);
