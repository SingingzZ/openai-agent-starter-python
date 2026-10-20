# -*- coding: utf-8 -*-
"""
本地自检脚本 —— 不启动 Agent，直接跑一遍出行决策的核心链路。

用途：确认 AMAP_API_KEY 配置正确、接口连通、推荐结果符合预期。

用法（在项目根目录执行）：

    python tools_check.py
    python tools_check.py "深圳北站" "喜茶、优衣库"
    python tools_check.py "红莲南路地铁站" "倍轻松、西厅村屋" --radius 8000
    python tools_check.py "红莲南路地铁站" "倍轻松、西厅村屋" --mode bus

参数说明：
    --radius  搜索半径（米），默认 5000
    --mode    出行方式 walk 步行 / drive 驾车 / bus 公交地铁
    --top     推荐几个商场
"""

from __future__ import annotations

import argparse
import os
import sys

# 让脚本可以直接从仓库根目录运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents._map_tools import AmapError, geocode, recommend_malls  # noqa: E402


def print_header(text: str) -> None:
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description="出行决策 Agent 本地自检")
    parser.add_argument("place", nargs="?", default="红莲南路地铁站", help="用户所在位置")
    parser.add_argument("brands", nargs="?", default="倍轻松、西厅村屋", help="想逛的品牌，顿号分隔")
    parser.add_argument("--radius", type=int, default=5000, help="搜索半径（米）")
    parser.add_argument("--mode", default="walk", choices=["walk", "drive", "bus"], help="出行方式")
    parser.add_argument("--top", type=int, default=3, help="推荐几个商场")
    args = parser.parse_args()

    if not (os.getenv("AMAP_API_KEY") or "").strip():
        print("× 未检测到 AMAP_API_KEY。请复制 .env.example 为 .env 并填入高德 Key。")
        return 1

    print_header(f"场景：我在「{args.place}」，想去一个有 {'、'.join(args.brands.split('、')) if '、' in args.brands else args.brands} 的商场")

    # 1. 定位
    try:
        origin = geocode(args.place)
    except AmapError as exc:
        print(f"× 定位失败：{exc}")
        return 1
    print(f"√ 定位成功：{origin['formatted_address']}  ({origin['location']})")

    # 2. 推荐
    try:
        result = recommend_malls(
            place=args.place,
            brands=args.brands,
            radius=args.radius,
            travel_mode=args.mode,
            top_n=args.top,
        )
    except AmapError as exc:
        print(f"× 检索失败：{exc}")
        return 1

    # 3. 品牌纠错提示
    for item in result["brands"]:
        if item["corrected"]:
            print(f"! 品牌名纠错：你说的「{item['input']}」应为「{item['name']}」"
                  f"（附近 {item['shop_count']} 家门店）")
        else:
            print(f"√ 品牌「{item['name']}」找到 {item['shop_count']} 家门店")

    # 4. 结果
    if not result.get("ok"):
        print(f"\n{result['message']}")
        for entry in result.get("partial", []):
            mall = entry["mall"]
            print(f"\n  · {mall['name']}（直线 {mall['distance_text']}）")
            print(f"    缺失品牌：{'、'.join(entry['missing_brands'])}")
            for shop in entry["shops"]:
                print(f"    有 {shop['brand']}：{shop['shop']}"
                      + (f"  [{shop['floor']}]" if shop["floor"] else ""))
        return 0

    for cand in result["candidates"]:
        mall = cand["mall"]
        trip = cand.get("trip")
        print(f"\n【推荐 {cand['rank']}】{mall['name']}")
        if trip:
            print(f"  {trip['mode']}：{trip['distance_text']}，{trip['duration_text']}")
        else:
            print(f"  直线距离：{mall['distance_text']}（路径规划未返回）")
        print(f"  地址：{mall['address']}")
        if mall["business_area"]:
            print(f"  商圈：{mall['business_area']}")
        if mall["open_time"]:
            print(f"  营业时间：{mall['open_time']}")
        for shop in cand["shops"]:
            line = f"  · {shop['brand']} → {shop['shop']}"
            if shop["floor"]:
                line += f"（{shop['floor']}）"
            print(line)
            print(f"     {shop['address']}")
            if shop["open_time"]:
                print(f"     营业 {shop['open_time']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
