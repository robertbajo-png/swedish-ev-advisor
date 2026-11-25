import React from 'react';

export function VehicleImageNotice({ car }) {
  return car.image && car.imageNotice ? <p className="vehicleImageNotice">{car.imageNotice}</p> : null;
}
