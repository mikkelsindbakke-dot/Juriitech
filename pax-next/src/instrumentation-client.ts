// Next.js client-instrumentation — kører tidligt i browseren ved hver
// page-load. Registrerer Sentry-client-init så uncaught exceptions
// i browseren fanges + PII scrubbes via beforeSend.
import "../sentry.client.config";
