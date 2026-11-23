import assert from 'node:assert/strict';
import {policy as kiaEv2} from './kia_ev2_publication.mjs';
import {policy as toyotaChrPlus} from './toyota_chr_plus_publication.mjs';
import {policy as volkswagenIdBuzz} from './volkswagen_id_buzz_publication.mjs';
import {policy as xpengG6} from './xpeng_g6_publication.mjs';
import {policy as xpengG9} from './xpeng_g9_publication.mjs';
import {policy as renault4Evolution} from './renault_4_evolution_publication.mjs';
import {policy as renault4Pair} from './renault_4_pair_publication.mjs';
import {policy as cupraTavascan} from './cupra_tavascan_drive_publication.mjs';
import {policy as polestar3} from './polestar_3_publication.mjs';
import {policy as ioniq5} from './hyundai_ioniq5_publication.mjs';
import {policy as fordPumaGenE} from './ford_puma_gen_e_publication.mjs';
import {policy as mercedesGlb} from './mercedes_glb_publication.mjs';
import {policy as ioniq9} from './hyundai_ioniq9_publication.mjs';
import {policy as porscheMacan} from './porsche_macan_publication.mjs';
const adapters=new Map([kiaEv2,toyotaChrPlus,volkswagenIdBuzz,xpengG6,xpengG9,renault4Evolution,renault4Pair,cupraTavascan,polestar3,ioniq5,fordPumaGenE,mercedesGlb,ioniq9,porscheMacan].map(policy=>[policy.adapter,policy]));
export function newModelAdapter(name){
 const adapter=adapters.get(name);assert(adapter,'Unregistered new-model adapter');return adapter;
}
