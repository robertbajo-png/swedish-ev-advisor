import { approvedNewsImage, isPublishedArticle } from './news-presentation.js';
import editorialPhotos from './news-editorial-images.json' with { type: 'json' };

export function editorialNewsImage(article) {
  if (!isPublishedArticle(article)) return null;
  const approved = approvedNewsImage(article);
  if (approved) return approved;
  // The registry contains reviewed illustrations bound to one published article.
  const photo = Object.hasOwn(editorialPhotos, article.slug) && editorialPhotos[article.slug];
  return photo && photo.article_id === article.id ? photo : null;
}
