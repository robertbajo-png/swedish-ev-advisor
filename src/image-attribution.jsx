
import React from 'react';
import { photoCredit } from './biljournal-images.js';

export function ImageAttribution({ car }) {
  const caption = car?.imageNotice || photoCredit(car?.image)?.model_image_notice;
  return car?.image && caption ? <p className="vehicleImageNotice">{caption}</p> : null;
}
