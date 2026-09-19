import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const root = path.join(process.cwd(), "..", "artifacts");
  const read = async (name: string) => {
    try {
      return JSON.parse(await readFile(path.join(root, name), "utf8"));
    } catch {
      return null;
    }
  };
  return NextResponse.json({
    frontier: await read("frontier.json"),
    ruleProof: await read("rule_proof.json"),
  });
}
