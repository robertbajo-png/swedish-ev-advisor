import {policy} from './lexus_rz_publication.mjs';
import {assertScopedPublishedRows,singleCatalogDelta} from './hyundai_inster_advanced_release_scope.mjs';
import {createSingleVariantReleaseScope,singleVariantReleaseHash,proveSingleVariantRelease} from './porsche_macan_release_scope.mjs';

const lexus={id:'lexus',label:'Lexus RZ',route:'https://elbilsagenten.se/bilar/lexus-rz-350e-executive',policy};
export const assertLexusPublishedRows=(rows,plan)=>assertScopedPublishedRows(rows,plan,policy);
export const lexusCatalogDelta=(baseline,rows,plan,options)=>singleCatalogDelta(baseline,rows,plan,policy,options);
export const createLexusReleaseScope=evidence=>createSingleVariantReleaseScope(evidence,lexus);
export const lexusReleaseHash=(scope,target)=>singleVariantReleaseHash(scope,target,lexus);
export const proveLexusRelease=(scope,fresh,target,seal,now)=>proveSingleVariantRelease(scope,fresh,target,seal,now,lexus);
