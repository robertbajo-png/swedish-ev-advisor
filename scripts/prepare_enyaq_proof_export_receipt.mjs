
import {readFile} from 'node:fs/promises';
import {prepareEnyaqProofExportReceipt,atomicJson} from './sync_public_catalog.mjs';
import assert from 'node:assert/strict';
const [livePath,beforePath,publishPath,outPath]=process.argv.slice(2);
assert(livePath&&beforePath&&publishPath&&outPath,'Usage: node scripts/prepare_enyaq_proof_export_receipt.mjs <live snapshot> <pre-write canonical readback> <saved successful publish packet> <output receipt>');
const receipt=prepareEnyaqProofExportReceipt(await readFile(livePath),JSON.parse(await readFile(beforePath,'utf8')),JSON.parse(await readFile(publishPath,'utf8')));
await atomicJson(outPath,receipt);
console.log(JSON.stringify({receipt_prepared:true,scope:receipt.kind,approved_targets:Object.keys(receipt.expected_proofs).length,remote_writes:false}));

