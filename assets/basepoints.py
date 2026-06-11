"""
宝可梦基础点数（努力值）数据 — 从 assets/basepoints.json 加载。
"""
import json
import os


def load_basepoints():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "basepoints.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


BASEPOINTS = load_basepoints()