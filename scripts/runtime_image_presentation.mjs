/** Project only the positioning records bound to the exact reviewed source bytes.
 * Full source and derivative digests remain in the checked-in audit registries. */
export function publicImagePresentation(presentation, responsive) {
  return { models: Object.values(presentation.models).filter(item =>
    item.status === 'approved' && typeof item.content_sha256 === 'string' &&
    responsive[item.asset_url]?.source_sha256 === item.content_sha256
  ).map(({ asset_url, object_fit, object_position }) => ({ asset_url, object_fit, object_position })) };
}
