import { z } from "zod";

export const commandSchema = z.string().trim().min(1).max(300);

export const pluginManifestSchema = z.object({
  id: z.string().min(2).max(64),
  name: z.string().min(2).max(80),
  version: z.string().min(1).max(20),
  description: z.string().min(1).max(300),
  entryCommand: z.string().min(1).max(120),
  permissionLevel: z.enum(["safe", "confirm", "admin"])
});
