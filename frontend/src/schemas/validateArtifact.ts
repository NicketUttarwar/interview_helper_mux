import { loadArtifactWriteSchema } from "./generated";

export async function validateArtifactWrite(
  path: string,
  data: unknown,
): Promise<{ ok: true } | { ok: false; errors: string[] }> {
  const schema = await loadArtifactWriteSchema(path);
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
