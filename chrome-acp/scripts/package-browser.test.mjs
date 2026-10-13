import {test} from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync, writeFileSync, rmSync, readFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {createHash} from "node:crypto";
import {cliVersion, NODE_VERSION, mergeManifest} from "./package-browser.mjs";

test("CLI versions accept releases and Python prereleases", () => {
  const directory = mkdtempSync(join(tmpdir(), "browser-version-test-"));
  const projectFile = join(directory, "pyproject.toml");
  try {
    for (const version of ["1.7.32", "1.7.32a1", "1.7.32b1", "1.7.32rc2"]) {
      writeFileSync(projectFile, `version = "${version}"\n`);
      assert.equal(cliVersion(projectFile), version);
    }
    for (const version of ["1_7_32_beta", "1.7.32b", "../1.7.32", "1.7.32/escape"]) {
      writeFileSync(projectFile, `version = "${version}"\n`);
      assert.throws(() => cliVersion(projectFile), /Invalid CLI release version/);
    }
  } finally {
    rmSync(directory, {recursive: true, force: true});
  }
});

test("manifest merge verifies artifact hashes and rejects duplicate platforms", () => {
  const directory = mkdtempSync(join(tmpdir(), "browser-manifest-test-"));
  try {
    const version = cliVersion();
    const filename = `siada-browser-${version}-linux-x64.zip`;
    const data = Buffer.from("synthetic artifact");
    writeFileSync(join(directory, filename), data);
    const part = {
      schema_version: 1, version, node_version: NODE_VERSION,
      platforms: {"linux-x64": {filename, sha256: createHash("sha256").update(data).digest("hex")}},
    };
    const input = join(directory, "part.json");
    const output = join(directory, "manifest.json");
    writeFileSync(input, JSON.stringify(part));
    mergeManifest([input], output);
    assert.deepEqual(JSON.parse(readFileSync(output)), part);
    assert.throws(() => mergeManifest([input, input], output), /duplicate/);
    writeFileSync(join(directory, filename), "corrupted");
    assert.throws(() => mergeManifest([input], output), /checksum/);
  } finally {
    rmSync(directory, {recursive: true, force: true});
  }
});