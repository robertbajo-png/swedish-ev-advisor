import assert from 'node:assert/strict';
import {policy as kiaEv2} from './kia_ev2_publication.mjs';
const adapters=new Map([[kiaEv2.adapter,kiaEv2]]);
export function newModelAdapter(name){
 const adapter=adapters.get(name);assert(adapter,'Unregistered new-model adapter');return adapter;
}
