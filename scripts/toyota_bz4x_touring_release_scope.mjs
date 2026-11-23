import {policy} from './toyota_bz4x_touring_publication.mjs';
import {assertScopedPublishedRows,singleCatalogDelta} from './hyundai_inster_advanced_release_scope.mjs';
import {createSingleVariantReleaseScope,singleVariantReleaseHash,proveSingleVariantRelease} from './porsche_macan_release_scope.mjs';

const touring={id:'touring',label:'Toyota bZ4X Touring',route:'https://elbilsagenten.se/bilar/toyota-bz4x-touring-active-tech-fwd',policy};
export const assertTouringPublishedRows=(rows,plan)=>assertScopedPublishedRows(rows,plan,policy);
export const touringCatalogDelta=(baseline,rows,plan,options)=>singleCatalogDelta(baseline,rows,plan,policy,options);
export const createTouringReleaseScope=evidence=>createSingleVariantReleaseScope(evidence,touring);
export const touringReleaseHash=(scope,target)=>singleVariantReleaseHash(scope,target,touring);
export const proveTouringRelease=(scope,fresh,target,seal,now)=>proveSingleVariantRelease(scope,fresh,target,seal,now,touring);
