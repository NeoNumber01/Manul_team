import MapLibreStops from "./components/MapLibreMap";

export default function App() {
  return (
    <div className="page">
      <header className="header">
        <h1>Public Transport Dashboard (Leaflet)</h1>
        <p>OSM basemap with MapLibre GL clustering.</p>
      </header>
      <main className="content">
        <MapLibreStops />
      </main>
    </div>
  );
}
