# -*- coding: utf-8 -*-
"""
Agent Tools — 出行决策 Agent 的工具集。

本文件以 `_` 开头，不会被 EdgeOne Makers 映射成路由，仅供 Agent 调用。
每个工具都基于 `agents/_map_tools.py`（高德地图数据层）实现，
如果需要换成腾讯位置服务，只改数据层即可，这里不用动。
"""

from __future__ import annotations

import json
from typing import Annotated

from agents import function_tool

from ._map_tools import (
    AmapError,
    format_distance,
    format_duration,
    geocode,
    normalize_mode,
    recommend_malls,
    resolve_brand,
    route,
    search_malls,
)


def _json(payload: dict) -> str:
    """统一输出，中文不转义，方便大模型直接读。"""
    return json.dumps(payload, ensure_ascii=False)


# ========== Tool 1：定位 ==========
@function_tool
def geocode_location(
    place: Annotated[str, "用户所在位置，可以是地铁站名、地名、地址，或 '116.336,39.877' 形式的经纬度"],
    city: Annotated[str, "所在城市，如 北京 / 深圳。可留空让系统自动判断"] = "",
) -> str:
    """把用户说的位置转换成经纬度坐标，用于后续附近检索。"""
    try:
        info = geocode(place, city)
    except AmapError as exc:
        return _json({"ok": False, "error": str(exc)})
    return _json({
        "ok": True,
        "place": place,
        "location": info["location"],
        "formatted_address": info["formatted_address"],
        "city": info["city"],
        "district": info["district"],
    })


# ========== Tool 2：附近商场 ==========
@function_tool
def search_nearby_malls(
    place: Annotated[str, "用户所在位置，地铁站名 / 地名 / 地址 / 经纬度"],
    radius: Annotated[int, "搜索半径，单位米，默认 5000"] = 5000,
    limit: Annotated[int, "最多返回几个商场，1-25，默认 10"] = 10,
    city: Annotated[str, "所在城市，可留空"] = "",
) -> str:
    """列出用户附近的商场，带直线距离、地址、营业时间、评分、所属商圈。"""
    try:
        origin = geocode(place, city)
        malls = search_malls(origin["location"], radius, limit=max(1, min(limit, 25)))
    except AmapError as exc:
        return _json({"ok": False, "error": str(exc)})

    return _json({
        "ok": True,
        "origin": origin["formatted_address"] or place,
        "radius_m": radius,
        "count": len(malls),
        "malls": [
            {
                "name": m["name"],
                "address": m["address"],
                "distance_text": format_distance(m["straight_distance"]),
                "straight_m": m["straight_distance"],
                "business_area": m["business_area"],
                "open_time": m["open_time"],
                "rating": m["rating"],
            }
            for m in malls
        ],
    })


# ========== Tool 3：某品牌的门店 ==========
@function_tool
def search_shop_nearby(
    place: Annotated[str, "用户所在位置，地铁站名 / 地名 / 地址 / 经纬度"],
    brand: Annotated[str, "品牌或店铺名，如 倍轻松 / 西町村屋 / 星巴克"],
    radius: Annotated[int, "搜索半径，单位米，默认 5000"] = 5000,
    city: Annotated[str, "所在城市，可留空"] = "",
) -> str:
    """查找某个品牌在用户附近的门店，自动纠正错别字（如 西厅村屋 → 西町村屋）。"""
    try:
        origin = geocode(place, city)
        resolved = resolve_brand(brand, origin["location"], radius, origin["city"] or city)
    except AmapError as exc:
        return _json({"ok": False, "error": str(exc)})

    return _json({
        "ok": bool(resolved["shops"]),
        "input": brand,
        "resolved_name": resolved["name"],
        "note": resolved["note"],
        "shops": [
            {
                "name": s["name"],
                "address": s["address"],
                "floor": s["floor"],
                "tel": s["tel"],
                "open_time": s["open_time"],
                "distance_text": format_distance(s["straight_distance"]),
                "straight_m": s["straight_distance"],
            }
            for s in resolved["shops"]
        ],
    })


# ========== Tool 4（核心）：同时满足多个品牌的商场推荐 ==========
@function_tool
def find_malls_with_shops(
    place: Annotated[str, "用户所在位置，如 红莲南路地铁站"],
    brands: Annotated[str, "想逛的品牌，多个用顿号/逗号分隔，如 倍轻松、西厅村屋"],
    radius: Annotated[int, "搜索半径，单位米，默认 5000"] = 5000,
    travel_mode: Annotated[str, "出行方式：walk 步行 / drive 驾车 / bus 公交地铁，默认 walk"] = "walk",
    top_n: Annotated[int, "推荐几个商场，1-5，默认 3"] = 3,
    city: Annotated[str, "所在城市，可留空"] = "",
) -> str:
    """
    找出同时包含全部指定品牌、且离用户最近的商场。

    这是本 Agent 的核心能力：先定位用户，再检索附近商场，
    对每个品牌做错别字纠正与门店召回，按"坐标邻近或名称命中"判断店铺是否在该商场内，
    最后按真实步行 / 驾车 / 公交距离排序给出推荐。
    """
    try:
        result = recommend_malls(
            place=place,
            brands=brands,
            radius=radius,
            travel_mode=travel_mode,
            top_n=top_n,
            city=city,
        )
    except AmapError as exc:
        return _json({"ok": False, "error": str(exc)})
    return _json(result)


# ========== Tool 5：路线规划 ==========
@function_tool
def plan_route(
    origin: Annotated[str, "出发地，地铁站名 / 地名 / 地址 / 经纬度"],
    destination: Annotated[str, "目的地，商场名 / 地名 / 地址 / 经纬度"],
    travel_mode: Annotated[str, "出行方式：walk 步行 / drive 驾车 / bus 公交地铁，默认 walk"] = "walk",
    city: Annotated[str, "所在城市，可留空"] = "",
) -> str:
    """规划从出发地到目的地的路线，给出距离与预计耗时。"""
    mode = normalize_mode(travel_mode)
    try:
        start = geocode(origin, city)
        end = geocode(destination, start["city"] or city)
        trip = route(start["location"], end["location"], mode, start["city"] or city)
    except AmapError as exc:
        return _json({"ok": False, "error": str(exc)})

    return _json({
        "ok": True,
        "from": start["formatted_address"] or origin,
        "to": end["formatted_address"] or destination,
        "mode": trip["label"],
        "distance_text": format_distance(trip["distance_m"]),
        "distance_m": trip["distance_m"],
        "duration_text": format_duration(trip["duration_s"]),
        "duration_s": trip["duration_s"],
        "summary": trip["summary"],
    })
