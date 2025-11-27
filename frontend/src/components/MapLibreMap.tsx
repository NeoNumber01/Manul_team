import { useEffect, useRef, useState } from "react";
import maplibregl, { Expression, LngLatBoundsLike, Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const OSM_RASTER_STYLE = {
  version: 8,
  sources: {
    "osm-tiles": {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: "osm-tiles",
      type: "raster",
      source: "osm-tiles",
    },
  ],
};

type Stop = {
  stop_id: string;
  stop_name: string;
  stop_lat: number;
  stop_lon: number;
};

type EdgeRecord = {
  from_stop_id: string;
  to_stop_id: string;
  from_lat: number;
  from_lon: number;
  to_lat: number;
  to_lon: number;
  trip_count?: number;
  avg_travel_time_sec?: number;
};

const clusterColors: Expression = [
  "step",
  ["get", "point_count"],
  "#9bbcff",
  50,
  "#7aa2ff",
  200,
  "#4c7cf0",
  500,
  "#2c5282",
];

const heatColors: Expression = [
  "interpolate",
  ["linear"],
  ["heatmap-density"],
  0,
  "rgba(255,255,204,0)",
  0.2,
  "rgba(255,237,160,0.5)",
  0.4,
  "rgba(254,217,118,0.7)",
  0.6,
  "rgba(254,178,76,0.85)",
  0.8,
  "rgba(253,141,60,0.9)",
  1,
  "rgba(227,26,28,0.95)",
];

export default function MapLibreStops() {
  const mapRef = useRef<MapLibreMap | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [count, setCount] = useState<number>(0);
  const [showHeat, setShowHeat] = useState(true);
  const [showClusters, setShowClusters] = useState(true);
  const [showStops, setShowStops] = useState(true);
  const [showEdges, setShowEdges] = useState(false);
  const [routeSrc, setRouteSrc] = useState("");
  const [routeDst, setRouteDst] = useState("");
  const [routeMsg, setRouteMsg] = useState<string | null>(null);

  useEffect(() => {
    // Initialize the map once
    if (!mapRef.current && containerRef.current) {
      const map = new maplibregl.Map({
        container: containerRef.current,
        style: OSM_RASTER_STYLE,
        center: [10.4515, 51.1657],
        zoom: 5.5,
        maxZoom: 18,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }));
      mapRef.current = map;
    }

    let disposed = false;
    const loadStopsAndEdges = async () => {
      try {
        setLoading(true);
        const [stopsRes, edgesRes] = await Promise.all([
          fetch(`${API_BASE}/api/stops`),
          fetch(`${API_BASE}/api/edges`),
        ]);
        if (!stopsRes.ok) throw new Error(`Stops API error ${stopsRes.status}`);
        if (!edgesRes.ok) throw new Error(`Edges API error ${edgesRes.status}`);
        const stops = (await stopsRes.json()) as Stop[];
        const edges = (await edgesRes.json()) as EdgeRecord[];
        if (disposed) return;
        setCount(stops.length);
        const geojson = {
          type: "FeatureCollection",
          features: stops.map((s) => ({
            type: "Feature",
            properties: {
              stop_id: s.stop_id,
              stop_name: s.stop_name,
            },
            geometry: {
              type: "Point",
              coordinates: [s.stop_lon, s.stop_lat],
            },
          })),
        } as GeoJSON.FeatureCollection;
        const edgesGeo = {
          type: "FeatureCollection",
          features: edges.map((e) => ({
            type: "Feature",
            properties: {
              from_stop_id: e.from_stop_id,
              to_stop_id: e.to_stop_id,
              trip_count: e.trip_count ?? 0,
              time_sec: e.avg_travel_time_sec ?? 0,
            },
            geometry: {
              type: "LineString",
              coordinates: [
                [e.from_lon, e.from_lat],
                [e.to_lon, e.to_lat],
              ],
            },
          })),
        } as GeoJSON.FeatureCollection;

        const map = mapRef.current;
        if (!map) return;
        const applyData = () => {
          if (map.getSource("stops")) {
            (map.getSource("stops") as maplibregl.GeoJSONSource).setData(geojson);
          } else {
            map.addSource("stops", {
              type: "geojson",
              data: geojson,
              cluster: true,
              clusterMaxZoom: 14,
              clusterRadius: 50,
            });

            map.addLayer({
              id: "stops-heat",
              type: "heatmap",
              source: "stops",
              paint: {
                "heatmap-radius": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  4,
                  10,
                  9,
                  25,
                ],
                "heatmap-opacity": 0.6,
                "heatmap-weight": 1,
                "heatmap-color": heatColors,
              },
              maxzoom: 12,
            });

            map.addLayer({
              id: "clusters",
              type: "circle",
              source: "stops",
              filter: ["has", "point_count"],
              paint: {
                "circle-color": clusterColors,
                "circle-radius": [
                  "step",
                  ["get", "point_count"],
                  12,
                  50,
                  16,
                  200,
                  22,
                  500,
                  28,
                ],
                "circle-opacity": 0.8,
                "circle-stroke-width": 1.2,
                "circle-stroke-color": "#0f172a",
              },
            });

            map.addLayer({
              id: "cluster-count",
              type: "symbol",
              source: "stops",
              filter: ["has", "point_count"],
              layout: {
                "text-field": ["get", "point_count_abbreviated"],
                "text-size": 12,
              },
              paint: {
                "text-color": "#ffffff",
              },
            });

            map.addLayer({
              id: "unclustered",
              type: "circle",
              source: "stops",
              filter: ["!", ["has", "point_count"]],
              paint: {
                "circle-color": "#d73a49",
                "circle-radius": 3,
                "circle-opacity": 0.8,
                "circle-stroke-width": 0.2,
                "circle-stroke-color": "#0f172a",
              },
            });
          }

          if (map.getSource("edges")) {
            (map.getSource("edges") as maplibregl.GeoJSONSource).setData(edgesGeo);
          } else {
            map.addSource("edges", {
              type: "geojson",
              data: edgesGeo,
              lineMetrics: true,
            });
            map.addLayer({
              id: "edges",
              type: "line",
              source: "edges",
              paint: {
                "line-color": "rgba(59,130,246,0.7)",
                "line-width": 1.2,
                "line-opacity": 0.5,
              },
            });
          }

          if (!map.getSource("route")) {
            map.addSource("route", {
              type: "geojson",
              data: { type: "FeatureCollection", features: [] },
            });
            map.addLayer({
              id: "route-line",
              type: "line",
              source: "route",
              filter: ["==", ["geometry-type"], "LineString"],
              paint: {
                "line-color": "#22c55e",
                "line-width": 3,
                "line-opacity": 0.9,
              },
            });
            map.addLayer({
              id: "route-points",
              type: "circle",
              source: "route",
              filter: ["==", ["geometry-type"], "Point"],
              paint: {
                "circle-color": "#22c55e",
                "circle-radius": 5,
                "circle-stroke-width": 1,
                "circle-stroke-color": "#0f172a",
              },
            });
          }

          map.on("click", "clusters", (e) => {
            const features = map.queryRenderedFeatures(e.point, { layers: ["clusters"] });
            if (!features.length) return;
            const clusterId = features[0].properties?.cluster_id;
            const source = map.getSource("stops") as maplibregl.GeoJSONSource;
            source.getClusterExpansionZoom(clusterId, (err, zoomTarget) => {
              if (err || zoomTarget === undefined) return;
              map.easeTo({
                center: (features[0].geometry as any).coordinates as [number, number],
                zoom: zoomTarget,
              });
            });
          });

          map.on("mouseenter", "clusters", () => {
            map.getCanvas().style.cursor = "pointer";
          });
          map.on("mouseleave", "clusters", () => {
            map.getCanvas().style.cursor = "";
          });
        };

        if (map.isStyleLoaded()) {
          applyData();
        } else {
          map.once("load", applyData);
        }
      } catch (err) {
        if (!disposed) setError((err as Error).message);
      } finally {
        if (!disposed) setLoading(false);
      }
    };
    loadStopsAndEdges();

    return () => {
      disposed = true;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const vis = (flag: boolean) => (flag ? "visible" : "none");
    const setVis = (layerId: string, flag: boolean) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, "visibility", vis(flag));
      }
    };
    setVis("stops-heat", showHeat);
    setVis("clusters", showClusters);
    setVis("cluster-count", showClusters);
    setVis("unclustered", showStops);
    setVis("edges", showEdges);
    setVis("route-line", true);
    setVis("route-points", true);
  }, [showHeat, showClusters, showStops, showEdges]);

  return (
    <div className="map-shell">
      <div ref={containerRef} className="maplibre-container" />
      <div className="map-overlay">
        {loading && <div className="pill">Loading data…</div>}
        {error && <div className="pill error">Error: {error}</div>}
        {!loading && !error && <div className="pill success">Stops: {count}</div>}
      </div>
      <div className="control-panel">
        <div className="control-group">
          <label>
            <input type="checkbox" checked={showHeat} onChange={(e) => setShowHeat(e.target.checked)} />
            Heatmap
          </label>
          <label>
            <input type="checkbox" checked={showClusters} onChange={(e) => setShowClusters(e.target.checked)} />
            Clusters
          </label>
          <label>
            <input type="checkbox" checked={showStops} onChange={(e) => setShowStops(e.target.checked)} />
            Stops
          </label>
          <label>
            <input type="checkbox" checked={showEdges} onChange={(e) => setShowEdges(e.target.checked)} />
            Edges
          </label>
        </div>
        <div className="control-group">
          <div className="route-row">
            <input
              className="route-input"
              placeholder="Start stop_id"
              value={routeSrc}
              onChange={(e) => setRouteSrc(e.target.value)}
            />
            <input
              className="route-input"
              placeholder="End stop_id"
              value={routeDst}
              onChange={(e) => setRouteDst(e.target.value)}
            />
            <button
              className="route-btn"
              onClick={async () => {
                setRouteMsg(null);
                if (!routeSrc || !routeDst) {
                  setRouteMsg("Enter both stop IDs");
                  return;
                }
                try {
                  const res = await fetch(
                    `${API_BASE}/api/route?src=${encodeURIComponent(routeSrc)}&dst=${encodeURIComponent(routeDst)}`,
                  );
                  if (!res.ok) throw new Error(`Route error ${res.status}`);
                  const data = await res.json();
                  const map = mapRef.current;
                  if (map && map.getSource("route")) {
                    (map.getSource("route") as maplibregl.GeoJSONSource).setData(data);
                    const stopIds = data.features[0]?.properties?.stop_ids || [];
                    setRouteMsg(`Path length: ${stopIds.length}`);
                  }
                } catch (err) {
                  setRouteMsg((err as Error).message);
                }
              }}
            >
              Route
            </button>
          </div>
          {routeMsg && <div className="pill">{routeMsg}</div>}
        </div>
      </div>
    </div>
  );
}
