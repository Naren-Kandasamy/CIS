import React from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

// Fix Leaflet's default icon issue with webpack/vite
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
    iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

interface CrimeMapProps {
  markers?: { position: [number, number], popup: string }[];
}

export default function CrimeMap({ markers }: CrimeMapProps) {
  // Center map on the first marker, or default to Bengaluru
  const centerPosition: [number, number] = markers && markers.length > 0 
    ? markers[0].position 
    : [12.9716, 77.5946];

  return (
    <div style={{ height: '400px', width: '100%', background: 'rgba(255,255,255,0.05)', borderRadius: '12px', padding: '16px', boxSizing: 'border-box' }}>
      <h3 style={{ color: 'white', marginBottom: '16px', fontSize: '16px', fontWeight: '500' }}>Geospatial Distribution</h3>
      <div style={{ height: 'calc(100% - 40px)', width: '100%', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', overflow: 'hidden' }}>
        <MapContainer key={`${centerPosition[0]}-${centerPosition[1]}`} center={centerPosition} zoom={12} style={{ height: '100%', width: '100%' }}>
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          />
          {markers && markers.length > 0 ? (
            markers.map((marker, idx) => (
              <Marker key={idx} position={marker.position}>
                <Popup>{marker.popup}</Popup>
              </Marker>
            ))
          ) : (
            <Marker position={centerPosition}>
              <Popup>Default Location</Popup>
            </Marker>
          )}
        </MapContainer>
      </div>
    </div>
  );
}
