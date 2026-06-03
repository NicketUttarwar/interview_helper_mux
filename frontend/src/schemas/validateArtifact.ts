import { artifactWriteSchemas } from "./generated";

export function validateArtifactWrite(
  path: string,
  data: unknown,
): { ok: true } | { ok: false; errors: string[] } {
  const schema = artifactWriteSchemas[path];
  if (!schema) {
    return { ok: true };
  }
  const result = schema.safeParse(data);
  if (result.success) {
    return { ok: true };
  }
  const errors = result.error.issues.map(
    (i) => `${i.path.join(".") || "(root)"}: ${i.message}`,
  );
  return { ok: false, errors: errors.slice(0, 12) };
}
