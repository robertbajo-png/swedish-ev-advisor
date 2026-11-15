import assert from 'node:assert/strict';
import {policy as kiaEv2} from './kia_ev2_publication.mjs';
import {policy as toyotaChrPlus} from './toyota_chr_plus_publication.mjs';
const adapters=new Map([[kiaEv2.adapter,kiaEv2],[toyotaChrPlus.adapter,toyotaChrPlus]]);
export function newModelAdapter(name){
 const adapter=adapters.get(name);assert(adapter,'Unregistered new-model adapter');return adapter;
}
