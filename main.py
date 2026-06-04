from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import requests
import re
import asyncio
from typing import Optional, Tuple, List, Dict

@register("EveMarket", "YourName", "EVE Online 市场查询插件 - 支持Jita、00星域、脑插批量查询", "1.0.0")
class EveMarketPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    # ==================== API 配置 ====================
    REGION_ID_FORGE = 10000002          # The Forge 区域（Jita所在）
    REGION_ID_PLEX_GLOBAL = 19000001    # PLEX 全球统一市场
    SYSTEM_ID_JITA = 30000142           # Jita 星系
    ESI_BASE = "https://esi.evetech.net/latest"
    
    # PLEX 配置
    PLEX_TYPE_ID = 44992
    PLEX_DEFAULT_QUANTITY = 500
    
    # ==================== 脑插系列映射 ====================
    IMPLANT_SERIES = {
        "圣光": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "护符": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "水晶": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "蝰蛇": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "强势": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "游牧者": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "百夫长": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "美德": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "采集": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "仿生": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "分裂": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "九头蛇": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "阿斯克雷": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
        "阿秋路": ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"],
    }
    
    # ==================== 00星域市场配置 ====================
    NULLSEC_MARKETS = {
        "delve": {
            "name": "Delve",
            "region_id": 10000064,
            "system_name": "1DQ1-A",
            "system_id": 30004759,
            "alliance": "Goonswarm",
            "description": "Goonswarm 主星域，有全00最活跃的市场"
        },
        "pureblind": {
            "name": "Pure Blind",
            "region_id": 10000032,
            "system_name": "Oijanen",
            "system_id": 30003845,
            "alliance": "Fraternity",
            "description": "Fraternity 星域，靠近帝国区"
        },
        "vale": {
            "name": "Vale of the Silent",
            "region_id": 10000046,
            "system_name": "R1O-GN",
            "system_id": 30004589,
            "alliance": "Fraternity",
            "description": "Fraternity 东部星域"
        },
        "providence": {
            "name": "Providence",
            "region_id": 10000040,
            "system_name": "Korsiki",
            "system_id": 30004420,
            "alliance": "Various",
            "description": "公开市场较多，离帝国区近"
        },
        "catch": {
            "name": "Catch",
            "region_id": 10000021,
            "system_name": "KDF-GY",
            "system_id": 30002657,
            "alliance": "Various",
            "description": "南方星域"
        },
        "impass": {
            "name": "Impass",
            "region_id": 10000025,
            "system_name": "GE-8JV",
            "system_id": 30002725,
            "alliance": "Various",
            "description": "南方星域"
        },
        "esoteria": {
            "name": "Esoteria",
            "region_id": 10000014,
            "system_name": "Q-HJ97",
            "system_id": 30002051,
            "alliance": "Various",
            "description": "南方星域"
        }
    }
    
    # ==================== 自定义星系市场配置 ====================
    CUSTOM_SYSTEM_MARKETS = {
        "c-j6mt": {
            "name": "C-J6MT",
            "region_id": 10000023,      # 因斯姆尔星域ID
            "system_id": 30000772,       # C-J6MT星系ID
            "description": "因斯姆尔星域，00区域",
            "keywords": ["c-j6mt", "c j6mt", "cj6mt"]
        },
        "1dq1-a": {
            "name": "1DQ1-A",
            "region_id": 10000064,
            "system_id": 30004759,
            "description": "Delve星域，Goonswarm总部",
            "keywords": ["1dq1-a", "1dq1a"]
        },
        "oijanen": {
            "name": "Oijanen",
            "region_id": 10000032,
            "system_id": 30003845,
            "description": "Pure Blind星域，Fraternity附近",
            "keywords": ["oijanen", "oi"]
        }
    }

    async def initialize(self):
        logger.info("EVE Market 插件已加载（全功能版）")

    async def terminate(self):
        logger.info("EVE Market 插件已卸载")

    # ==================== 基础查询方法 ====================
    
    @staticmethod
    def get_type_id_by_name_fuzzwork(name: str) -> Optional[int]:
        """通过 fuzzwork 查询物品ID（英文名）"""
        url = "https://www.fuzzwork.co.uk/api/typeid.php"
        params = {"typename": name}
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and data:
                return data[0].get("typeID")
            elif isinstance(data, dict) and "typeID" in data:
                return data["typeID"]
        except Exception as e:
            logger.error(f"fuzzwork 查询失败: {e}")
        return None

    @staticmethod
    def get_type_id_by_name_esi(name: str) -> Optional[int]:
        """通过 ESI 查询物品ID（支持中文）"""
        url = "https://esi.evetech.net/latest/universe/ids/"
        headers = {"Accept-Language": "zh"}
        try:
            resp = requests.post(url, headers=headers, json=[name], timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            inv_types = data.get("inventory_types") or []
            if not inv_types:
                return None
            return inv_types[0].get("id")
        except Exception as e:
            logger.error(f"ESI 查询失败: {e}")
        return None

    def search_inventory_types(self, search_string: str, strict: bool = False) -> Optional[List[Tuple[int, str]]]:
        """模糊搜索物品"""
        url = f"{self.ESI_BASE}/v3/search/"
        params = {
            "categories": "inventory_type",
            "search": search_string,
        }
        if strict:
            params["strict"] = "true"
        
        headers = {"Accept-Language": "zh", "User-Agent": "AstrBot-EVE-Market-Plugin/1.0"}
        
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code != 200:
                return None
            
            data = resp.json()
            type_ids = data.get("inventory_type", [])
            
            if not type_ids:
                return None
            
            results = []
            for type_id in type_ids[:10]:
                name = self.get_type_name_by_id(type_id)
                results.append((type_id, name))
            
            return results
        except Exception as e:
            logger.error(f"搜索出错: {e}")
            return None

    def get_type_name_by_id(self, type_id: int) -> Optional[str]:
        """根据ID获取物品名称"""
        url = f"{self.ESI_BASE}/universe/types/{type_id}/"
        headers = {"Accept-Language": "zh"}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("name")
        except Exception as e:
            logger.error(f"获取名称失败: {e}")
        return None

    def get_type_id_by_name(self, name: str, use_fuzzy: bool = True) -> Tuple[Optional[int], Optional[List[Tuple[int, str]]]]:
        """综合查询物品ID"""
        type_id = self.get_type_id_by_name_fuzzwork(name)
        if type_id:
            return type_id, None
        
        type_id = self.get_type_id_by_name_esi(name)
        if type_id:
            return type_id, None
        
        if use_fuzzy:
            fuzzy_results = self.search_inventory_types(name)
            if fuzzy_results and len(fuzzy_results) > 0:
                return fuzzy_results[0][0], fuzzy_results
        
        return None, None

    def parse_query_input(self, input_str: str) -> Tuple[str, int, str]:
        """解析用户输入，提取物品名称、数量和脑插级别前缀"""
        input_str = input_str.strip()
        
        quantity = 1
        name_part = input_str
        
        # 数量在后面的格式
        pattern_qty_suffix = r'^(.+?)\s*[×x*]\s*(\d+)$'
        match = re.match(pattern_qty_suffix, input_str, re.IGNORECASE)
        if match:
            name_part = match.group(1).strip()
            quantity = int(match.group(2))
        
        # 数量在前面的格式
        pattern_qty_prefix = r'^(\d+)\s*[×x*]\s*(.+?)$'
        match = re.match(pattern_qty_prefix, input_str, re.IGNORECASE)
        if match:
            name_part = match.group(2).strip()
            quantity = int(match.group(1))
        
        # 提取脑插级别前缀
        level_prefix = ""
        if name_part.startswith("低级"):
            level_prefix = "低级"
            name_part = name_part[2:]
        elif name_part.startswith("中级"):
            level_prefix = "中级"
            name_part = name_part[2:]
        
        return name_part, quantity, level_prefix

    def is_implant_series_query(self, name: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """判断是否是脑插系列查询"""
        level_prefix = ""
        search_name = name
        if search_name.startswith("低级"):
            level_prefix = "低级"
            search_name = search_name[2:]
        elif search_name.startswith("中级"):
            level_prefix = "中级"
            search_name = search_name[2:]
        
        for series in self.IMPLANT_SERIES.keys():
            if search_name == series:
                return True, series, level_prefix
        
        return False, None, None

    def get_price_by_region(self, type_id: int, region_id: int, filter_system_id: int = None) -> Tuple[Optional[float], Optional[float]]:
        """获取指定区域/星系的价格"""
        page = 1
        sell_prices = []
        buy_prices = []

        while True:
            url = f"{self.ESI_BASE}/markets/{region_id}/orders/"
            params = {
                "order_type": "all",
                "page": page,
                "type_id": type_id,
            }
            try:
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                orders = resp.json()
            except Exception as e:
                logger.error(f"获取订单失败: {e}")
                return None, None

            if not orders:
                break

            for order in orders:
                # 如果指定了星系ID，只取该星系的订单
                if filter_system_id is not None and order.get("system_id") != filter_system_id:
                    continue
                
                price = order["price"]
                if order["is_buy_order"]:
                    buy_prices.append(price)
                else:
                    sell_prices.append(price)

            x_pages = resp.headers.get("X-Pages")
            if x_pages is None or page >= int(x_pages):
                break
            page += 1

        min_sell = min(sell_prices) if sell_prices else None
        max_buy = max(buy_prices) if buy_prices else None
        return min_sell, max_buy

    def get_price_by_name_general(self, name: str, quantity: int = 1, region_id: int = None, system_id: int = None) -> Tuple[Optional[int], Optional[float], Optional[float], Optional[List]]:
        """通用价格查询"""
        # PLEX 特殊处理
        if region_id is None and name.lower() == "plex":
            region_id = self.REGION_ID_PLEX_GLOBAL
            if quantity == 1:
                quantity = self.PLEX_DEFAULT_QUANTITY
        
        type_id, fuzzy_results = self.get_type_id_by_name(name)
        if not type_id:
            return None, None, None, fuzzy_results
        
        # 默认使用 Jita 区域
        if region_id is None:
            region_id = self.REGION_ID_FORGE
            system_id = self.SYSTEM_ID_JITA
        
        unit_sell, unit_buy = self.get_price_by_region(type_id, region_id, system_id)
        total_sell = unit_sell * quantity if unit_sell else None
        total_buy = unit_buy * quantity if unit_buy else None
        
        return type_id, total_sell, total_buy, fuzzy_results

    def get_implant_slot(self, name: str) -> str:
        """获取脑插插槽位置"""
        slot_map = {
            "阿尔法": "1号槽 (感知)",
            "贝它": "2号槽 (记忆)",
            "伽玛": "3号槽 (毅力)",
            "德尔塔": "4号槽 (智力)",
            "伊普西隆": "5号槽 (魅力)",
            "欧米伽": "6号槽 (套装效果)"
        }
        
        for key, slot in slot_map.items():
            if key in name:
                return slot
        return None

    # ==================== 脑插批量查询 ====================
    
    async def query_implant_series(self, series_name: str, level_prefix: str) -> str:
        """批量查询脑插系列价格"""
        grades = self.IMPLANT_SERIES[series_name]
        results = []
        
        for grade in grades:
            if level_prefix:
                full_name = f"{level_prefix}{series_name}-{grade}"
            else:
                full_name = f"{series_name}-{grade}"
            
            type_id, total_sell, total_buy, fuzzy = self.get_price_by_name_general(full_name)
            
            if type_id and total_sell:
                results.append({
                    "grade": grade.replace("型", ""),
                    "sell": total_sell,
                    "buy": total_buy,
                })
            else:
                results.append({
                    "grade": grade.replace("型", ""),
                    "sell": None,
                    "buy": None,
                })
            
            await asyncio.sleep(0.3)
        
        # 构建输出
        output_lines = [
            f"🧠 **{level_prefix}{series_name} 系列脑插价格**",
            "",
            "┌────┬──────────────────┬──────────────────┬────────────┐",
            "│ 槽位 │ 最低卖价           │ 最高买价           │ 差价       │",
            "├────┼──────────────────┼──────────────────┼────────────┤"
        ]
        
        slot_names = ["1号", "2号", "3号", "4号", "5号", "6号"]
        
        for i, r in enumerate(results):
            slot = slot_names[i] if i < len(slot_names) else f"{i+1}号"
            
            if r["sell"] is not None:
                sell_text = f"{r['sell']:>13,.0f} ISK"
                buy_text = f"{r['buy']:>13,.0f} ISK" if r["buy"] else f"{'无订单':>13}"
                
                if r["buy"]:
                    spread = r["sell"] - r["buy"]
                    spread_pct = (spread / r["buy"]) * 100
                    spread_text = f"{spread_pct:>5.1f}%"
                else:
                    spread_text = "无买单"
                
                output_lines.append(f"│ {slot} │ {sell_text} │ {buy_text} │ {spread_text:>10} │")
            else:
                output_lines.append(f"│ {slot} │ {'--- 无订单 ---':>13} │ {'--- 无订单 ---':>13} │ {'无法获取':>10} │")
        
        output_lines.append("└────┴──────────────────┴──────────────────┴────────────┘")
        
        if level_prefix == "低级":
            output_lines.extend(["", "📦 **套装效果**: 低级系列 6件套 +25% 次要效果"])
        elif level_prefix == "中级":
            output_lines.extend(["", "📦 **套装效果**: 中级系列 6件套 +50% 次要效果"])
        else:
            output_lines.extend([
                "",
                "📦 **套装效果**: 标准系列 6件套 +100% 次要效果",
                "",
                "💡 各部位作用: 1号感知 | 2号记忆 | 3号毅力 | 4号智力 | 5号魅力 | 6号套装"
            ])
        
        return "\n".join(output_lines)

    # ==================== 命令实现 ====================
    
    @filter.command(".jita")
    async def jita(self, event: AstrMessageEvent, content_message: str = ""):
        """查询 Jita 市场价格，支持普通物品、PLEX、脑插"""
        if not content_message:
            yield event.plain_result(
                "📋 **市场查询帮助**\n\n"
                "🔹 **普通物品查询**\n"
                "  .jita [物品名]          - 查询价格\n"
                "  .jita [物品名] x[数量]  - 查询多个数量\n"
                "  .jita PLEX              - 查询500 PLEX\n\n"
                "🔹 **脑插批量查询**\n"
                "  .jita [系列名]          - 查询全套脑插\n"
                "  .jita 低级[系列名]      - 查询低级系列\n"
                "  .jita 中级[系列名]      - 查询中级系列\n\n"
                "🔹 **单个脑插查询**\n"
                "  .jita [名称]-[级别]     - 查询单个脑插\n\n"
                "📖 **示例**:\n"
                "  .jita Tritanium\n"
                "  .jita PLEX x1000\n"
                "  .jita 圣光\n"
                "  .jita 圣光-阿尔法型\n\n"
                "🌌 00市场: .null [星域名] [物品名]\n"
                "🚀 自定义星系: .c [星系名] [物品名]"
            )
            return
        
        item_name, quantity, level_prefix = self.parse_query_input(content_message)
        
        # 检查是否是脑插系列批量查询
        is_series, series_name, detected_level = self.is_implant_series_query(item_name)
        
        if is_series and quantity == 1:
            final_level = detected_level if detected_level else level_prefix
            result = await self.query_implant_series(series_name, final_level)
            yield event.plain_result(result)
            return
        
        # 普通物品或单个脑插查询
        type_id, total_sell, total_buy, fuzzy = self.get_price_by_name_general(item_name, quantity)
        
        if not type_id:
            if fuzzy:
                msg = f"❌ 未找到「{item_name}」，相关物品：\n"
                for i, (tid, tname) in enumerate(fuzzy[:5]):
                    msg += f"  {i+1}. {tname} (ID: {tid})\n"
                msg += "\n💡 使用 .jitaid [ID] 直接查询"
                yield event.plain_result(msg)
            else:
                yield event.plain_result(f"❌ 未找到物品「{item_name}」")
            return
        
        is_plex = item_name.lower() == "plex" or type_id == self.PLEX_TYPE_ID
        
        if total_sell is None and total_buy is None:
            yield event.plain_result(f"「{item_name}」当前没有订单")
            return
        
        unit_sell = total_sell / quantity if total_sell else None
        unit_buy = total_buy / quantity if total_buy else None
        
        is_implant = any(g in item_name for g in ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"])
        slot = self.get_implant_slot(item_name) if is_implant else None
        
        result_parts = []
        
        if quantity > 1:
            result_parts.append(f"📦 **{item_name}** x {quantity}")
        else:
            result_parts.append(f"📦 **{item_name}**")
        
        if slot:
            result_parts.append(f"📌 **插槽**: {slot}")
        
        if is_plex:
            result_parts.append("🌍 市场: PLEX 全球统一市场")
        else:
            result_parts.append("📍 市场: Jita (The Forge)")
        
        if total_sell:
            result_parts.append(f"💰 最低卖价: {total_sell:,.2f} ISK")
            if quantity > 1 and unit_sell:
                result_parts.append(f"   (单价: {unit_sell:,.2f} ISK)")
        else:
            result_parts.append(f"💰 最低卖价: 无订单")
        
        if total_buy:
            result_parts.append(f"💎 最高买价: {total_buy:,.2f} ISK")
            if quantity > 1 and unit_buy:
                result_parts.append(f"   (单价: {unit_buy:,.2f} ISK)")
        else:
            result_parts.append(f"💎 最高买价: 无订单")
        
        if total_sell and total_buy:
            spread = total_sell - total_buy
            spread_pct = (spread / total_buy) * 100
            result_parts.append(f"📊 差价: {spread:,.2f} ISK ({spread_pct:.1f}%)")
        
        if is_implant:
            for series in self.IMPLANT_SERIES.keys():
                if series in item_name:
                    result_parts.append(f"\n💡 批量查询: .jita {series}")
                    break
        
        yield event.plain_result("\n".join(result_parts))

    @filter.command(".jitaid")
    async def jita_by_id(self, event: AstrMessageEvent, type_id_str: str):
        """通过 Type ID 查询 Jita 价格"""
        try:
            type_id = int(type_id_str.strip())
        except ValueError:
            yield event.plain_result("❌ 请提供正确的 Type ID")
            return
        
        unit_sell, unit_buy = self.get_price_by_region(type_id, self.REGION_ID_FORGE, self.SYSTEM_ID_JITA)
        
        if unit_sell is None and unit_buy is None:
            yield event.plain_result(f"Type ID {type_id} 在 Jita 没有订单")
            return
        
        result_parts = [f"📦 **Type ID: {type_id}**"]
        
        if unit_sell:
            result_parts.append(f"💰 最低卖价: {unit_sell:,.2f} ISK")
        if unit_buy:
            result_parts.append(f"💎 最高买价: {unit_buy:,.2f} ISK")
        
        if unit_sell and unit_buy:
            spread = unit_sell - unit_buy
            spread_pct = (spread / unit_buy) * 100
            result_parts.append(f"📊 差价: {spread:,.2f} ISK ({spread_pct:.1f}%)")
        
        yield event.plain_result("\n".join(result_parts))

    @filter.command(".null")
    async def query_nullsec(self, event: AstrMessageEvent, market_name: str = "", item_name: str = ""):
        """查询00星域市场价格"""
        if not market_name:
            lines = ["🌌 **00星域市场查询**", "", "用法: .null [星域名] [物品名]", "", "📋 支持的市场:"]
            for key, market in self.NULLSEC_MARKETS.items():
                lines.append(f"  • {key:<12} - {market['name']} ({market['alliance']})")
            lines.extend(["", "💡 示例: .null delve Tritanium", "      .null pureblind PLEX"])
            yield event.plain_result("\n".join(lines))
            return
        
        if not item_name:
            yield event.plain_result(f"请提供物品名称\n示例: .null {market_name} Tritanium")
            return
        
        market_key = market_name.lower()
        if market_key not in self.NULLSEC_MARKETS:
            available = ", ".join(self.NULLSEC_MARKETS.keys())
            yield event.plain_result(f"❌ 未知市场: {market_name}\n支持的市场: {available}")
            return
        
        market = self.NULLSEC_MARKETS[market_key]
        
        yield event.plain_result(f"🔍 正在查询 {market['name']} 市场的 {item_name}...\n📍 星系: {market['system_name']} | 🏢 联盟: {market['alliance']}")
        
        item_clean, quantity, _ = self.parse_query_input(item_name)
        type_id, total_sell, total_buy, fuzzy = self.get_price_by_name_general(item_clean, quantity, market["region_id"], market["system_id"])
        
        if not type_id:
            yield event.plain_result(f"❌ 未找到物品「{item_clean}」")
            return
        
        if total_sell is None and total_buy is None:
            yield event.plain_result(f"「{item_clean}」在 {market['name']} 没有公开订单")
            return
        
        # 获取 Jita 价格对比
        _, jita_sell, jita_buy, _ = self.get_price_by_name_general(item_clean)
        
        unit_sell = total_sell / quantity if total_sell else None
        
        result_parts = [
            f"🌌 **{market['name']} 市场**",
            f"📍 {market['system_name']} | 🏢 {market['alliance']}",
            "",
            f"📦 **{item_clean}**" + (f" x {quantity}" if quantity > 1 else ""),
        ]
        
        if total_sell:
            result_parts.append(f"💰 最低卖价: {total_sell:,.2f} ISK")
        else:
            result_parts.append(f"💰 最低卖价: 无公开订单")
        
        if total_buy:
            result_parts.append(f"💎 最高买价: {total_buy:,.2f} ISK")
        else:
            result_parts.append(f"💎 最高买价: 无公开订单")
        
        if jita_sell and total_sell:
            premium = (total_sell - jita_sell * quantity) / (jita_sell * quantity) * 100
            result_parts.extend(["", f"📊 **与Jita对比**"])
            result_parts.append(f"   Jita卖价: {jita_sell * quantity:,.2f} ISK")
            result_parts.append(f"   {market['name']} 溢价: +{premium:.1f}%" if premium > 0 else f"   {market['name']} 差价: {premium:.1f}%")
        
        yield event.plain_result("\n".join(result_parts))

    @filter.command(".c")
    async def query_custom_system(self, event: AstrMessageEvent, system_name: str = "", item_name: str = ""):
        """查询自定义星系市场价格（如 C-J6MT）"""
        if not system_name:
            lines = ["🚀 **自定义星系市场查询**", "", "用法: .c [星系代码] [物品名]", "", "📋 支持的星系:"]
            for key, market in self.CUSTOM_SYSTEM_MARKETS.items():
                lines.append(f"  • {key:<10} - {market['name']}")
                lines.append(f"    {market['description']}")
            lines.extend(["", "💡 示例: .c c-j6mt Tritanium", "      .c 1dq1-a Vexor"])
            yield event.plain_result("\n".join(lines))
            return
        
        if not item_name:
            yield event.plain_result(f"请提供物品名称\n示例: .c {system_name} Tritanium")
            return
        
        sys_key = system_name.lower()
        if sys_key not in self.CUSTOM_SYSTEM_MARKETS:
            matched = None
            for key, market in self.CUSTOM_SYSTEM_MARKETS.items():
                if sys_key in market["keywords"]:
                    matched = key
                    break
            if not matched:
                available = ", ".join(self.CUSTOM_SYSTEM_MARKETS.keys())
                yield event.plain_result(f"❌ 未找到星系: {system_name}\n支持的星系: {available}")
                return
            sys_key = matched
        
        market = self.CUSTOM_SYSTEM_MARKETS[sys_key]
        
        yield event.plain_result(f"🔍 正在查询 {market['name']} 市场的 {item_name}...")
        
        item_clean, quantity, _ = self.parse_query_input(item_name)
        type_id, total_sell, total_buy, fuzzy = self.get_price_by_name_general(item_clean, quantity, market["region_id"], market["system_id"])
        
        if not type_id:
            yield event.plain_result(f"❌ 未找到物品「{item_clean}」")
            return
        
        if total_sell is None and total_buy is None:
            yield event.plain_result(f"「{item_clean}」在 {market['name']} 没有公开订单")
            return
        
        _, jita_sell, jita_buy, _ = self.get_price_by_name_general(item_clean)
        
        result_parts = [
            f"🚀 **{market['name']} 市场**",
            f"📍 星系: {market['name']}",
            "",
            f"📦 **{item_clean}**" + (f" x {quantity}" if quantity > 1 else ""),
        ]
        
        if total_sell:
            result_parts.append(f"💰 最低卖价: {total_sell:,.2f} ISK")
        else:
            result_parts.append(f"💰 最低卖价: 无公开订单")
        
        if total_buy:
            result_parts.append(f"💎 最高买价: {total_buy:,.2f} ISK")
        else:
            result_parts.append(f"💎 最高买价: 无公开订单")
        
        if jita_sell and total_sell:
            premium = (total_sell - jita_sell * quantity) / (jita_sell * quantity) * 100
            result_parts.extend(["", f"📊 **与Jita对比**"])
            result_parts.append(f"   Jita卖价: {jita_sell * quantity:,.2f} ISK")
            result_parts.append(f"   {market['name']} 溢价: +{premium:.1f}%" if premium > 0 else f"   {market['name']} 差价: {premium:.1f}%")
        
        yield event.plain_result("\n".join(result_parts))

    @filter.command(".brainlist")
    async def brain_list(self, event: AstrMessageEvent):
        """查看支持的脑插系列列表"""
        series_list = "、".join(self.IMPLANT_SERIES.keys())
        yield event.plain_result(
            f"🧠 **支持查询的脑插系列**\n\n"
            f"{series_list}\n\n"
            f"📋 **使用方式**:\n"
            f"  .jita [系列名]      - 查询标准系列\n"
            f"  .jita 低级[系列名]  - 查询低级系列\n"
            f"  .jita 中级[系列名]  - 查询中级系列\n"
            f"  .jita [名称]-[级别] - 查询单个脑插\n\n"
            f"📖 **示例**:\n"
            f"  .jita 圣光\n"
            f"  .jita 低级圣光\n"
            f"  .jita 圣光-阿尔法型"
        )

    @filter.command(".search")
    async def search_item(self, event: AstrMessageEvent):
        """模糊搜索物品"""
        content = event.message_str.strip()
        parts = content.split()
        
        if len(parts) < 2:
            yield event.plain_result("用法: .search [物品名称]\n例如: .search Rifter\n      .search 圣光")
            return
        
        search_name = " ".join(parts[1:])
        yield event.plain_result(f"🔍 正在搜索: {search_name}...")
        
        results = self.search_inventory_types(search_name)
        
        if not results:
            yield event.plain_result(f"❌ 未找到: {search_name}\n\n💡 尝试使用英文名称")
            return
        
        lines = [f"🔍 搜索结果: {search_name}", ""]
        for i, (tid, tname) in enumerate(results[:10]):
            lines.append(f"  {i+1}. {tname} (ID: {tid})" if tname else f"  {i+1}. Type ID: {tid}")
        
        lines.append("\n💡 使用 .jitaid [ID] 查询价格")
        yield event.plain_result("\n".join(lines))

    @filter.command(".help")
    async def help_cmd(self, event: AstrMessageEvent):
        """显示帮助信息"""
        yield event.plain_result(
            "📚 **EVE Market 插件帮助**\n\n"
            "🔹 **市场查询**\n"
            "  .jita [物品名]          - 查询Jita价格\n"
            "  .jita [物品名] x[数量]  - 查询多个数量\n"
            "  .jita PLEX              - 查询500 PLEX\n"
            "  .jitaid [ID]            - 通过Type ID查询\n\n"
            "🔹 **00星域市场**\n"
            "  .null [星域名] [物品名] - 查询星域市场\n"
            "  支持: delve, pureblind, vale, providence, catch\n\n"
            "🔹 **自定义星系市场**\n"
            "  .c [星系代码] [物品名]  - 查询星系市场\n"
            "  支持: c-j6mt, 1dq1-a, oijanen\n\n"
            "🔹 **脑插查询**\n"
            "  .jita [系列名]          - 批量查询\n"
            "  .brainlist              - 查看支持系列\n\n"
            "🔹 **搜索**\n"
            "  .search [名称]          - 模糊搜索物品\n\n"
            "📖 **示例**:\n"
            "  .jita Tritanium\n"
            "  .jita 圣光\n"
            "  .null delve Vexor\n"
            "  .c c-j6mt PLEX"
        )
