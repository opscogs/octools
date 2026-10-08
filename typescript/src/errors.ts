/**
 * The error a descriptor or a converter raises, and the language-neutral
 * error codes the spec fixtures express failures with.
 *
 * @module
 */

/**
 * Raised when an `OCTool` is constructed or converted with invalid data.
 *
 * Envelope parsing raises the schema library's own error instead
 * (`ZodError`), and malformed JSON text raises `SyntaxError`.
 */
export class OCToolError extends Error {
  /** Build the error with a message for a person. */
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "OCToolError";
  }
}

/**
 * The codes a spec fixture's `expected` uses for an operation that fails
 * (`{"error": "<code>"}`). They name the failure, not an exception type, so
 * every implementation maps its own errors onto them. Internal to the
 * conformance runner; the package root does not export them.
 */
export const ERROR_CODES = [
  "invalid_descriptor",
  "invalid_name",
  "invalid_envelope",
  "invalid_style",
] as const;

/** One of {@link ERROR_CODES}. */
export type ErrorCode = (typeof ERROR_CODES)[number];
