/**
 * Conformance findings shared by the schema checker and the validators.
 *
 * A finding is plain data: a library asserts `findings` equal `[]` in its
 * own tests and gets a readable diff when something drifts.
 *
 * @module
 */

/** The fields a {@link Finding} is constructed from. */
export interface FindingInit {
  /** Stable snake_case identifier of the rule that fired. */
  readonly rule: string;
  /** Explains the problem for a person; not part of the contract. */
  readonly message: string;
  /** The descriptor the finding concerns; `null` for a bare schema check. */
  readonly tool?: string | null;
  /** JSON pointer to where the problem is, where that applies. */
  readonly path?: string | null;
}

/**
 * One conformance problem.
 *
 * `rule` is a stable snake_case identifier for the rule that fired,
 * `message` explains it for a person, `tool` names the descriptor it
 * concerns (`null` for a bare schema check), and `path` is a JSON pointer
 * where that applies. Instances are frozen; build a changed copy with
 * `new Finding({ ...finding, tool: "name" })`.
 */
export class Finding {
  /** Stable snake_case identifier of the rule that fired. */
  readonly rule: string;
  /** Explains the problem for a person; not part of the contract. */
  readonly message: string;
  /** The descriptor the finding concerns; `null` for a bare schema check. */
  readonly tool: string | null;
  /** JSON pointer to where the problem is, or `null`. */
  readonly path: string | null;

  /** Build a frozen finding; `tool` and `path` default to `null`. */
  constructor(init: FindingInit) {
    this.rule = init.rule;
    this.message = init.message;
    this.tool = init.tool ?? null;
    this.path = init.path ?? null;
    Object.freeze(this);
  }
}
