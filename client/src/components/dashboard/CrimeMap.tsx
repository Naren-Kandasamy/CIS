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

const DEFAULT_MARKERS = [
  { position: [12.9716, 77.5946] as [number, number], popup: 'Bengaluru City HQ: Active Monitoring' },
  { position: [15.8497, 74.4977] as [number, number], popup: 'Belagavi District: 10 Incidents Logged' },
  { position: [12.2958, 76.6394] as [number, number], popup: 'Mysuru District: 4 Incidents Logged' },
  { position: [15.3647, 75.1240] as [number, number], popup: 'Hubballi-Dharwad: 6 Incidents Logged' },
  { position: [12.9141, 74.8560] as [number, number], popup: 'Mangaluru District: 3 Incidents Logged' }
];

interface CrimeMapProps {
  markers?: { position: [number, number], popup: string }[];
}

export default function CrimeMap({ markers }: CrimeMapProps) {
  const hasMarkers = markers && markers.length > 0;
  const mapMarkers = hasMarkers ? markers : DEFAULT_MARKERS;
  // Center map on the first marker, or default to middle of Karnataka to show all pins
  const centerPosition: [number, number] = hasMarkers 
    ? markers[0].position 
    : [14.0000, 76.2500];
  const zoomLevel = hasMarkers ? 12 : 7;

  return (
    <div style={{ height: '400px', width: '100%', padding: '8px', boxSizing: 'border-box' }}>
      <h3 style={{ color: 'white', marginBottom: '16px', fontSize: '15px', fontWeight: '500' }}>Geospatial Distribution</h3>
      <div style={{ height: 'calc(100% - 40px)', width: '100%', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', overflow: 'hidden' }}>
        <MapContainer key={`${centerPosition[0]}-${centerPosition[1]}`} center={centerPosition} zoom={zoomLevel} style={{ height: '100%', width: '100%' }}>
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          />
          {mapMarkers.map((marker, idx) => (
            <Marker key={idx} position={marker.position}>
              <Popup>{marker.popup}</Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </div>
  );
}
