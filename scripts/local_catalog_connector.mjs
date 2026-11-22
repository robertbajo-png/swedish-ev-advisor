import assert from 'node:assert/strict';
import { realpath } from 'node:fs/promises';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export const CATALOG_PROJECT = 'eutcryxbitudllcnpnex';

export async function catalogConnectorPath(root, input) {
  const file = input ? resolve(input) : join(root, 'data','local','db-tools','source-client.mjs');
  assert.equal(await realpath(file), file, 'Require the existing unlinked source connector');
  const sourceRoot = resolve(dirname(file), '../../..');
  assert.equal(file, join(sourceRoot, 'data','local','db-tools','source-client.mjs'));
  assert(!/[\\/]onedrive(?:commercial|consumer)?(?:[\\/]|$)/i.test(sourceRoot));
  const rel = relative(join(sourceRoot, 'data','local','release-data'), root);
  assert(root === sourceRoot || (rel && !rel.startsWith('..') && !isAbsolute(rel)), 'Connector is outside the source project');
  return {file, sourceRoot};
}

export async function openCatalogSnapshot({file, sourceRoot}) {
  const connector = await import(pathToFileURL(file).href);
  assert.equal(connector.PROJECT_REF, CATALOG_PROJECT);
  const cwd = process.cwd();
  let client;
  try {
    process.chdir(sourceRoot);
    client = await connector.openSourceSnapshot();
  } finally {
    process.chdir(cwd);
  }
  return {client, close: () => connector.closeSourceSnapshot(client)};
}
