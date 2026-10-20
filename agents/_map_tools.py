# -*- coding: utf-8 -*-
"""
高德地图 Web 服务 API 封装 —— 出行决策 Agent 的数据层。

本模块只负责"取数"，不含 Agent 逻辑，方便单独验证与复用。
对外提供的能力：

    geocode()          地名/地址 → 经纬度
    search_malls()    周边商场检索
    search_shops()    周边门店检索
    suggest_names()   错别字纠错（"西厅村屋" → "西町村屋"）
    resolve_brand()   品牌名纠错 + 门店召回（含自动扩大搜索半径）
    match_shop_mall()  门店是否落在某商场内（坐标邻近 或 名称命中）
    route()           路径规划（步行 / 驾车 / 公交）

文档：https://lbs.amap.com/api/webservice/guide/api/search
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
AMAP_BASE = "https://restapi.amap.com/v3"
DEFAULT_TIMEOUT = 12.0

# 060100 = 购物服务/商场，其子类 060101 购物中心、060102 普通商场 都会被召回
MALL_TYPECODE = "060100"

# 门店坐标与商场坐标相距多少米以内，才有资格视为"这家店在这个商场里"。
# 实际观察到商场内店铺通常在 100 米内，而相邻的两座商场往往相隔 200~400 米，
# 因此这里取 150 米，并配合下面的门牌号校验一起用。
INDOOR_MATCH_METERS = 150

# 这些错误码表示"稍等再来"，可以退避重试
RETRYABLE_INFOCODES = {"10021", "10023"}

# 召回不到时，依次把这些半径放大倍数作为兜底（基于用户给定的半径）
RADIUS_FALLBACK_FACTORS = (1, 2, 4)

ROUTE_PATHS = {
    "walk": "direction/walking",
    "drive": "direction/driving",
    "bus": "direction/transit/integrated",
}

ROUTE_LABELS = {"walk": "步行", "drive": "驾车", "bus": "公交地铁"}

# 形如 "116.336,39.877" 或 "116.336 39.877" 的坐标串
_LNGLAT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)[,，\s]+(-?\d+(?:\.\d+)?)\s*$")
# 形如 "3F层"、"F3层"、"4楼"、"B1层"
_FLOOR_RE = re.compile(r"(\d+\s*[Ff]\s*层|[Ff]\s*\d+\s*层|\d+\s*楼|[BbLl]\s*\d+\s*层)")


class AmapError(RuntimeError):
    """高德接口调用失败。"""


# ---------------------------------------------------------------------------
# 基础请求
# ---------------------------------------------------------------------------
def _amap_get(path: str, **params: Any) -> dict:
    """调用高德 Web 服务接口，统一处理鉴权与错误码。"""
    api_key = (os.getenv("AMAP_API_KEY") or "").strip()
    if not api_key:
        raise AmapError(
            "AMAP_API_KEY 未配置。请在高德开放平台申请「Web服务」类型的 Key，"
            "并写入项目根目录的 .env 文件：AMAP_API_KEY=你的Key"
        )

    params["key"] = api_key
    params.setdefault("output", "JSON")

    url = f"{AMAP_BASE}/{path}?" + urllib.parse.urlencode(params)

    # 免费版 Key 有并发上限，偶发 10021（并发超限）/ 10023（配额超限）时退避重试
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=DEFAULT_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise AmapError(f"接口返回 HTTP {exc.code}：{exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise AmapError(f"网络请求失败：{exc.reason}") from exc

        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise AmapError(f"接口返回的不是合法 JSON：{exc}") from exc

        if data.get("status") == "1":
            return data

        infocode = str(data.get("infocode"))
        if infocode in RETRYABLE_INFOCODES and attempt < 2:
            time.sleep(0.5 * (attempt + 1))
            continue
        raise AmapError(f"高德接口报错：{data.get('info')}（infocode={infocode}）")

    raise AmapError(f"高德接口报错：{data.get('info')}（infocode={data.get('infocode')}）")


def parse_lnglat(text: str | None) -> str | None:
    """把肉眼坐标串规范化成高德要求的 "lng,lat"，非法输入返回 None。"""
    if not text:
        return None
    match = _LNGLAT_RE.match(text)
    if not match:
        return None
    lng, lat = float(match.group(1)), float(match.group(2))
    # 粗略判断落在中国版图内，避免把别的数据误当成坐标
    if not (73.0 < lng < 136.0 and 3.0 < lat < 54.0):
        return None
    return f"{lng:.6f},{lat:.6f}"


def haversine(a: str, b: str) -> float:
    """两个 "lng,lat" 之间的球面距离，单位：米。"""
    lng1, lat1 = (float(x) for x in a.split(","))
    lng2, lat2 = (float(x) for x in b.split(","))
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def _as_dict(value: Any) -> dict:
    """高德个别字段在部分版本里会退化成 JSON 字符串，统一转成 dict。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def extract_floor(*texts: str | None) -> str:
    """从名称/地址里抽取楼层信息，如 "丽泽路300号…3F层3F-14" → "3F层"。"""
    for text in texts:
        if not text:
            continue
        match = _FLOOR_RE.search(text)
        if match:
            return match.group(1).replace(" ", "")
    return ""


def strip_branches(name: str | None) -> str:
    """去掉分店括号，如 "西町村屋(北京apm店)" → "西町村屋"。"""
    if not name:
        return ""
    return re.sub(r"[（(].*?[)）]", "", name).strip()


# ---------------------------------------------------------------------------
# POI 归一化
# ---------------------------------------------------------------------------
def _poi(poi: dict) -> dict:
    """把高德 POI 原始结构裁剪成我们关心的字段。"""
    biz = _as_dict(poi.get("biz_ext"))
    location = poi.get("location") or ""
    return {
        "id": poi.get("id", ""),
        "name": poi.get("name", ""),
        "address": poi.get("address", ""),
        "location": location,
        "typecode": poi.get("typecode", ""),
        "type": poi.get("type", ""),
        "business_area": poi.get("business_area", ""),
        "city": poi.get("cityname", ""),
        "district": poi.get("adname", ""),
        "tel": poi.get("tel", ""),
        "rating": biz.get("rating", ""),
        "open_time": biz.get("opentime2") or biz.get("open_time") or "",
        "floor": extract_floor(poi.get("address"), poi.get("name")),
        # 高德周边搜索自带到中心点的直线距离（米），可直接用来排序
        "straight_distance": int(poi.get("distance") or 0),
    }


# ---------------------------------------------------------------------------
# 地理编码
# ---------------------------------------------------------------------------
def geocode(place: str, city: str = "") -> dict:
    """地名/地址 → 经纬度。输入本身是坐标则直接返回。"""
    direct = parse_lnglat(place)
    if direct:
        return {
            "location": direct,
            "formatted_address": place,
            "city": city,
            "district": "",
            "level": "坐标",
        }

    def _call(with_city: bool) -> dict:
        params: dict[str, Any] = {"address": place}
        if with_city and city:
            params["city"] = city
        return _amap_get("geocode/geo", **params)

    # 带上城市能提高准确度；但用户说的城市与实际不符时会报错，此时去掉城市重试
    try:
        data = _call(True)
    except AmapError:
        data = _call(False) if city else None
        if data is None:
            raise

    geocodes = data.get("geocodes") or []
    if not geocodes:
        raise AmapError(f"没有找到“{place}”的坐标，请换个更具体的说法（可加上城市名）")

    first = geocodes[0]
    return {
        "location": first.get("location", ""),
        "formatted_address": first.get("formatted_address", ""),
        "city": first.get("city") or city,
        "district": first.get("district") or "",
        "level": first.get("level", ""),
    }


# ---------------------------------------------------------------------------
# 搜索
# ---------------------------------------------------------------------------
def search_malls(
    location: str,
    radius: int = 5000,
    limit: int = 25,
    keyword: str = "",
) -> list[dict]:
    """周边商场检索，按距离由近到远。"""
    params: dict[str, Any] = {
        "location": location,
        "types": MALL_TYPECODE,
        "radius": radius,
        "sortrule": "distance",
        "offset": min(limit, 25),
        "page": 1,
        "extensions": "all",
    }
    if keyword:
        params["keywords"] = keyword
    data = _amap_get("place/around", **params)
    return [_poi(p) for p in (data.get("pois") or [])]


def search_shops(
    location: str,
    keyword: str,
    radius: int = 5000,
    limit: int = 20,
) -> list[dict]:
    """周边门店检索（品牌专柜 / 餐厅 / 任意 POI 名）。"""
    data = _amap_get(
        "place/around",
        location=location,
        keywords=keyword,
        radius=radius,
        sortrule="distance",
        offset=min(limit, 25),
        page=1,
        extensions="all",
    )
    return [_poi(p) for p in (data.get("pois") or [])]


def suggest_names(keyword: str, city: str = "") -> list[str]:
    """
    输入提示接口 —— 兼做错别字纠错。

    用户说的 "西厅村屋" 在高德里其实叫 "西町村屋"，
    直接搜索会召回 0 条，而这个接口能给出正确的品牌名。
    """
    params: dict[str, Any] = {"keywords": keyword, "datatype": "poi"}
    if city:
        params["city"] = city
    try:
        data = _amap_get("assistant/inputtips", **params)
    except AmapError:
        return []

    names: list[str] = []
    for tip in data.get("tips") or []:
        if not isinstance(tip, dict) or not tip.get("name"):
            continue
        base = strip_branches(tip["name"])
        # 去掉 breo / BREO 这类品牌英文前缀
        base = re.sub(r"^breo", "", base, flags=re.IGNORECASE).strip()
        if base and base not in names:
            names.append(base)
    return names


def resolve_brand(
    keyword: str,
    origin: str,
    radius: int = 5000,
    city: str = "",
) -> dict:
    """
    品牌名纠错 + 门店召回。

    三级兜底：
      1. 原名直接搜；
      2. 用输入提示接口纠正后重搜；
      3. 逐步放大搜索半径（1x → 2x → 4x）。

    返回 {"name", "shops", "note", "fixed"}。
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return {"name": "", "shops": [], "note": "品牌名为空", "fixed": False}

    # 1. 原名
    for factor in RADIUS_FALLBACK_FACTORS:
        shops = search_shops(origin, keyword, radius * factor)
        if shops:
            return {"name": keyword, "shops": shops, "note": "", "fixed": False}

    # 2. 纠正后重搜
    for candidate in suggest_names(keyword, city):
        if candidate == keyword:
            continue
        for factor in RADIUS_FALLBACK_FACTORS:
            shops = search_shops(origin, candidate, radius * factor)
            if shops:
                return {
                    "name": candidate,
                    "shops": shops,
                    "note": f"输入提示将“{keyword}”纠正为“{candidate}”",
                    "fixed": True,
                }

    return {
        "name": keyword,
        "shops": [],
        "note": f"在半径 {radius * RADIUS_FALLBACK_FACTORS[-1]} 米内没有找到“{keyword}”",
        "fixed": False,
    }


def _batches(items: list[str], size: int) -> list[list[str]]:
    """把关键词列表切成每批 size 个，避免单次请求的关键词串过长。"""
    return [items[i:i + size] for i in range(0, len(items), size)]


def resolve_brands(brand_list: list[str], origin: str, radius: int = 5000, city: str = "") -> list[dict]:
    """
    批量解析品牌名 —— resolve_brand 的批量版。

    高德周边搜索支持用 "|" 分隔多个关键词，所以把多个品牌合并成一次请求，
    回来再按品牌名在本地分组；这样 2~3 个品牌只需 1 次请求，
    而不是每个品牌各发 3~7 次，能显著降低触发 10021（并发超限）的概率。

    返回 [{"input", "name", "shops", "note", "fixed"}, ...]
    """
    entries = [
        {"input": b, "name": b, "shops": [], "note": "", "fixed": False}
        for b in brand_list
    ]

    def collect(names: list[str], search_radius: int) -> None:
        """合并查询一批品牌，按品牌名把 POI 分组回填。"""
        if not names:
            return
        pois = search_shops(origin, "|".join(names), search_radius, limit=25)
        for entry in entries:
            if entry["shops"] or entry["name"] not in names:
                continue
            entry["shops"] = [p for p in pois if entry["name"] in p["name"]]

    # 第 1 轮：用用户写的原名查
    for batch in _batches([e["name"] for e in entries], 3):
        collect(batch, radius)

    # 第 2 轮：没结果的先做错别字纠正，再合并查一次
    if any(not e["shops"] for e in entries):
        for entry in entries:
            if entry["shops"]:
                continue
            for candidate in suggest_names(entry["name"], city):
                if candidate != entry["name"]:
                    entry["name"] = candidate
                    entry["fixed"] = True
                    entry["note"] = f"输入提示将“{entry['input']}”纠正为“{candidate}”"
                    break
        for batch in _batches([e["name"] for e in entries if not e["shops"]], 3):
            collect(batch, radius)

    # 第 3 轮：还是没有，就逐步放大半径（同样合并成一次请求）
    for factor in (2, 4):
        missing = [e["name"] for e in entries if not e["shops"]]
        if not missing:
            break
        for batch in _batches(missing, 3):
            collect(batch, radius * factor)

    for entry in entries:
        if not entry["shops"]:
            entry["note"] = f"在半径 {radius * RADIUS_FALLBACK_FACTORS[-1]} 米内没有找到“{entry['name']}”"
    return entries


def _address_number(text: str) -> str:
    """从地址里取出门牌号，如 "丽泽路18号首创中心2F层" → "18"。"""
    numbers = re.findall(r"(\d+)\s*号", text or "")
    return numbers[-1] if numbers else ""


def _address_conflict(shop: dict, mall: dict) -> bool:
    """
    门牌号对不上，说明只是靠得近、并非同一处。

    典型误判：优衣库在"丽泽路18号首创中心"，而丽泽天街在"丽泽路300号"，
    两者直线距离很近，但根本不是同一个商场。
    只要有一方没写门牌号，就不下这个判断（信息不足时宁可放过）。
    """
    shop_no = _address_number(shop.get("address", ""))
    mall_no = _address_number(mall.get("address", ""))
    if not shop_no or not mall_no:
        return False
    return shop_no != mall_no


def _name_hit(shop: dict, mall: dict) -> str:
    """
    门店名/地址里是否出现了商场名。

    例：门店 "breo倍轻松(龙湖北京丽泽天街店)" 命中商场 "龙湖北京丽泽天街"。
    分店名里常带括号，所以全称和去括号主干都试一遍。
    返回命中的那个商场名，没命中返回空串。
    """
    mall_name = (mall.get("name") or "").strip()
    candidates = [mall_name, strip_branches(mall_name)]
    targets = [shop.get("name") or "", shop.get("address") or ""]
    for probe in candidates:
        if len(probe) < 2:
            continue
        for target in targets:
            if probe in target:
                return probe
    return ""


def locate_shop(
    shop: dict,
    malls: list[dict],
    threshold: int = INDOOR_MATCH_METERS,
) -> dict | None:
    """
    给一家门店找唯一的归属商场。

    之所以强调"唯一"：商场之间可能只隔几十米（深圳龙华的百易广场 A 栋/B 栋），
    若允许多个商场共用同一家店，就会出现"隔壁商场的店被算进我家"的假推荐。

    判定优先级：
      1. 名称命中 —— 门店名/地址里直接写明了商场名，最可靠；
      2. 坐标邻近 —— 退而求其次，取距离最近且不超过 threshold 米的那个商场。

    返回 {"index", "distance_m", "evidence"}，归属不上返回 None。
    """
    if not shop.get("location"):
        return None

    name_hit: tuple[float, int] | None = None
    coord_hit: tuple[float, int] | None = None

    for idx, mall in enumerate(malls):
        if not mall.get("location"):
            continue
        distance = haversine(shop["location"], mall["location"])
        if _name_hit(shop, mall):
            if name_hit is None or distance < name_hit[0]:
                name_hit = (distance, idx)
        elif distance <= threshold and not _address_conflict(shop, mall):
            if coord_hit is None or distance < coord_hit[0]:
                coord_hit = (distance, idx)

    if name_hit:
        distance, idx = name_hit
        return {
            "index": idx,
            "distance_m": int(distance),
            "evidence": f"店铺信息中写明位于“{_name_hit(shop, malls[idx])}”",
        }
    if coord_hit:
        distance, idx = coord_hit
        return {
            "index": idx,
            "distance_m": int(distance),
            "evidence": f"与商场相距约 {int(distance)} 米",
        }
    return None


# ---------------------------------------------------------------------------
# 路径规划
# ---------------------------------------------------------------------------
def route(origin: str, destination: str, mode: str = "walk", city: str = "") -> dict:
    """路径规划。mode: walk / drive / bus。"""
    path = ROUTE_PATHS.get(mode, ROUTE_PATHS["walk"])
    params: dict[str, Any] = {"origin": origin, "destination": destination}
    if mode == "bus" and city:
        params["city1"] = city
        params["city2"] = city

    data = _amap_get(path, **params)
    payload = data.get("route") or {}
    result = {"mode": mode, "label": ROUTE_LABELS.get(mode, mode), "distance_m": 0, "duration_s": 0, "summary": ""}

    if mode == "bus":
        transits = payload.get("transits") or []
        if not transits:
            return result
        first = transits[0]
        # 公交方案的字段都是字符串，且时长直接挂在 duration 上（单位秒）
        result["distance_m"] = int(float(first.get("distance") or payload.get("distance") or 0))
        try:
            result["duration_s"] = int(float(first.get("duration") or 0))
        except (TypeError, ValueError):
            result["duration_s"] = 0

        steps: list[str] = []
        for seg in first.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            bus = _as_dict(seg.get("bus"))
            buslines = bus.get("buslines") or []
            if buslines and isinstance(buslines[0], dict):
                line = (buslines[0].get("name") or "").strip()
                if line:
                    # "M340路(深圳北站--大浪宝坤工业区)" 只保留线路号，避免太长
                    steps.append(line.split("(")[0].strip() or line)
            walking = _as_dict(seg.get("walking"))
            walk_m = walking.get("distance")
            if walk_m and str(walk_m) != "0":
                steps.append(f"步行 {walk_m} 米")
        result["summary"] = " → ".join(steps)
        return result

    paths = payload.get("paths") or []
    if paths:
        first = paths[0]
        result["distance_m"] = int(float(first.get("distance") or 0))
        result["duration_s"] = int(float(first.get("duration") or 0))
        steps = first.get("steps") or []
        if steps and isinstance(steps[0], dict):
            result["summary"] = (steps[0].get("instruction") or "").replace("<![CDATA[", "").replace("]]>", "")
    return result


# ---------------------------------------------------------------------------
# 组合能力：同时满足多个品牌的商场推荐
# ---------------------------------------------------------------------------
# 最多对多少个候选商场做真实路径规划（避免打太多接口）
MAX_ROUTE_CALLS = 10


def split_brands(raw: str) -> list[str]:
    """把 "倍轻松、西厅村屋" / "倍轻松和西町村屋" 拆成品牌列表。"""
    if not raw:
        return []
    parts = re.split(r"[,，、;；/和与及]+", raw)
    return [p.strip() for p in parts if p.strip()]


def normalize_mode(mode: str) -> str:
    """把中文出行方式统一成 walk / drive / bus。"""
    mode = (mode or "").strip().lower()
    if mode in ROUTE_PATHS:
        return mode
    if mode in ("步行", "走路"):
        return "walk"
    if mode in ("驾车", "开车", "打车"):
        return "drive"
    if mode in ("公交", "地铁", "公共交通", "公交地铁"):
        return "bus"
    return "walk"


def recommend_malls(
    place: str,
    brands: str,
    radius: int = 5000,
    travel_mode: str = "walk",
    top_n: int = 3,
    city: str = "",
) -> dict:
    """
    核心算法：找出同时包含全部指定品牌、且离用户最近的商场。

    流程：
      定位 → 召回周边商场 → 逐个品牌纠错并召回门店
      → 判断门店是否落在商场内（坐标邻近 或 名称命中）
      → 对候选做真实路径规划 → 按出行距离排序
    """
    mode = normalize_mode(travel_mode)
    brand_list = split_brands(brands)

    origin = geocode(place, city)
    origin_loc = origin["location"]
    malls = search_malls(origin_loc, radius, limit=25)
    resolved = resolve_brands(brand_list, origin_loc, radius, origin["city"] or city)

    # 每家门店只归属一个商场，避免相邻商场共用同一家门店
    mall_hits: list[list[dict]] = [[] for _ in malls]
    for item in resolved:
        for shop in item["shops"]:
            owner = locate_shop(shop, malls)
            if owner is None:
                continue
            mall_hits[owner["index"]].append({
                "brand": item["name"],
                "shop": shop["name"],
                "address": shop["address"],
                "floor": shop["floor"],
                "tel": shop["tel"],
                "open_time": shop["open_time"],
                "evidence": owner["evidence"],
                "match_distance_m": owner["distance_m"],
            })

    # 同一商场里若有多家同品牌门店，只保留离商场最近的那家，输出更干净
    for idx, hits in enumerate(mall_hits):
        nearest: dict[str, dict] = {}
        for hit in sorted(hits, key=lambda h: h["match_distance_m"]):
            nearest.setdefault(hit["brand"], hit)
        mall_hits[idx] = list(nearest.values())

    full: list[dict] = []
    partial: list[dict] = []

    for idx, mall in enumerate(malls):
        hits = mall_hits[idx]
        if not hits:
            continue
        present = {h["brand"] for h in hits}
        missing = [item["name"] for item in resolved if item["name"] not in present]

        record = {
            "mall": {
                "name": mall["name"],
                "address": mall["address"],
                "location": mall["location"],
                "straight_m": mall["straight_distance"],
                "distance_text": format_distance(mall["straight_distance"]),
                "business_area": mall["business_area"],
                "open_time": mall["open_time"],
                "rating": mall["rating"],
            },
            "shops": hits,
            "missing_brands": missing,
            "trip": None,
        }

        if missing:
            partial.append(record)
        else:
            full.append(record)

    # 只对最近的若干个候选做真实路径规划，控制接口调用次数
    full.sort(key=lambda r: r["mall"]["straight_m"])
    for record in full[:MAX_ROUTE_CALLS]:
        try:
            trip = route(origin_loc, record["mall"]["location"], mode, origin["city"] or city)
            if not trip or not trip["distance_m"]:
                # 选定的出行方式规划不出路线时，退回步行距离，保证排序和展示不缺数据
                trip = route(origin_loc, record["mall"]["location"], "walk", origin["city"] or city)
                if trip:
                    trip["label"] = f"{trip['label']}（{ROUTE_LABELS[mode]}无方案，已按步行估算）"
        except AmapError:
            trip = None
        if trip and trip["distance_m"]:
            record["trip"] = {
                "mode": trip["label"],
                "distance_m": trip["distance_m"],
                "distance_text": format_distance(trip["distance_m"]),
                "duration_s": trip["duration_s"],
                "duration_text": format_duration(trip["duration_s"]),
                "summary": trip["summary"],
            }

    full.sort(key=lambda r: (r["trip"] or {}).get("distance_m") or r["mall"]["straight_m"])
    partial.sort(key=lambda r: r["mall"]["straight_m"])

    brands_summary = [
        {
            "input": original,
            "name": item["name"],
            "corrected": item["fixed"],
            "note": item["note"],
            "shop_count": len(item["shops"]),
        }
        for original, item in zip(brand_list, resolved)
    ]

    payload = {
        "origin": origin["formatted_address"] or place,
        "origin_location": origin_loc,
        "travel_mode": ROUTE_LABELS[mode],
        "brands": brands_summary,
        "radius_m": radius,
    }

    if not full:
        payload.update({
            "ok": False,
            "reason": "no_full_match",
            "message": (
                f"在 {radius} 米内没有同时包含「{'、'.join(brand_list)}」的商场，"
                "以下为部分满足的商场，供取舍。"
            ),
            "partial": [
                {
                    "mall": r["mall"],
                    "shops": [{k: v for k, v in s.items() if k != "match_distance_m"} for s in r["shops"]],
                    "missing_brands": r["missing_brands"],
                }
                for r in partial[:3]
            ],
        })
        return payload

    payload.update({
        "ok": True,
        "candidates": [
            {
                "rank": idx + 1,
                "mall": r["mall"],
                "trip": r["trip"],
                "shops": [{k: v for k, v in s.items() if k != "match_distance_m"} for s in r["shops"]],
            }
            for idx, r in enumerate(full[: max(1, min(top_n, 5))])
        ],
    })
    return payload


def format_distance(meters: int) -> str:
    """1200 → "1.2 公里"，不足 1 公里时显示米。"""
    if meters >= 1000:
        return f"{meters / 1000:.1f} 公里"
    return f"{meters} 米"


def format_duration(seconds: int) -> str:
    """1403 → "约 23 分钟"。"""
    if seconds <= 0:
        return "未知"
    minutes = max(1, round(seconds / 60))
    if minutes >= 60:
        return f"约 {minutes // 60} 小时 {minutes % 60} 分钟"
    return f"约 {minutes} 分钟"
