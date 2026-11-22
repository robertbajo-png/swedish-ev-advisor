import assert from 'node:assert/strict';
import {policy as kiaEv2} from './kia_ev2_publication.mjs';
import {policy as toyotaChrPlus} from './toyota_chr_plus_publication.mjs';
import {policy as volkswagenIdBuzz} from './volkswagen_id_buzz_publication.mjs';
import {policy as xpengG6} from './xpeng_g6_publication.mjs';
import {policy as xpengG9} from './xpeng_g9_publication.mjs';
import {policy as renault4Evolution} from './renault_4_evolution_publication.mjs';
import {policy as renault4Pair} from './renault_4_pair_publication.mjs';
import {policy as cupraTavascan} from './cupra_tavascan_drive_publication.mjs';
const adapters=new Map([kiaEv2,toyotaChrPlus,volkswagenIdBuzz,xpengG6,xpengG9,renault4Evolution,renault4Pair,cupraTavascan].map(policy=>[policy.adapter,policy]));
export function newModelAdapter(name){
 const adapter=adapters.get(name);assert(adapter,'Unregistered new-model adapter');return adapter;
}
