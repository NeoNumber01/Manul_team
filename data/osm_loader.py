# data/osm_loader.py
import requests
import json
import os
import streamlit as st

class RailDataLoader:
    def __init__(self, filename="data/german_railway_network.json"):
        # 自动处理路径，确保文件存在 data 目录下
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # 如果传入的文件名只是文件名，拼接路径；如果是路径，直接用
        if "data" not in filename:
             self.filepath = os.path.join(base_dir, filename)
        else:
             self.filepath = filename

    def load_or_fetch_data(self):
        """尝试加载本地地图，如果没有，就去下载"""
        if os.path.exists(self.filepath):
            # st.success(f"已加载本地路网底图") # 调试用，演示时注释掉
            with open(self.filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return self._fetch_from_overpass()

    def _fetch_from_overpass(self):
        # 这是一个查询德国主要干线的请求
        query = """
        [out:json][timeout:180];
        (
          way["railway"="rail"]["usage"="main"](47.0,5.5,55.5,15.5);
        );
        out geom;
        """
        url = "http://overpass-api.de/api/interpreter"

        try:
            print("正在从 OpenStreetMap 下载德国路网 (这可能需要 1-2 分钟)...")
            response = requests.get(url, params={'data': query})
            response.raise_for_status()
            data = response.json()

            geojson = self._convert_overpass_to_geojson(data)

            # 保存到本地，下次秒开
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(geojson, f)

            return geojson
        except Exception as e:
            print(f"地图下载失败: {e}")
            return None

    def _convert_overpass_to_geojson(self, overpass_data):
        features = []
        for element in overpass_data.get('elements', []):
            if element['type'] == 'way' and 'geometry' in element:
                coords = [[pt['lon'], pt['lat']] for pt in element['geometry']]
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords
                    },
                    "properties": element.get('tags', {})
                }
                features.append(feature)
        return {"type": "FeatureCollection", "features": features}