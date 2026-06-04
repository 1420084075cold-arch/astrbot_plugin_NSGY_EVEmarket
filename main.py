from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import requests
import re
import asyncio
from typing import Optional, Tuple, List, Dict

@register("EveMarket", "YourName", "EVE Online 市场查询插件，支持Jita价格、PLEX、模糊搜索和脑插批量查询", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    # 定义区域ID常量
    REGION_ID_FORGE = 10000002
    REGION_ID_PLEX_GLOBAL = 19000001
    SYSTEM_ID_JITA = 30000142
    ESI_BASE = "https://esi.evetech.net/latest"
    
    # PLEX 相关常量
    PLEX_TYPE_ID = 44992
    PLEX_DEFAULT_QUANTITY = 500
    
    # 脑插系列映射表
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

    async def initialize(self):
        logger.info("EVE Market 插件已加载（含脑插查询）")

    async def terminate(self):
        logger.info("EVE Market 插件已卸载")

    # ==================== 基础查询方法 ====================
    
    @staticmethod
    def get_type_id_by_name_fuzzwork(name: str) -> Optional[int]:
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
        """解析用户输入，提取物品名称、数量和脑插级别前缀
        
        返回: (item_name, quantity, level_prefix)
        level_prefix: "" 标准, "低级", "中级"
        """
        input_str = input_str.strip()
        
        # 提取数量
        quantity = 1
        name_part = input_str
        
        # 数量在后面的格式: 物品名 x100
        pattern_qty_suffix = r'^(.+?)\s*[×x*]\s*(\d+)$'
        match = re.match(pattern_qty_suffix, input_str, re.IGNORECASE)
        if match:
            name_part = match.group(1).strip()
            quantity = int(match.group(2))
        
        # 数量在前面的格式: 100x 物品名
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
        """判断是否是脑插系列查询（如"圣光"、"低级圣光"）
        
        返回: (is_series, series_name, level_prefix)
        """
        # 提取级别前缀
        level_prefix = ""
        search_name = name
        if search_name.startswith("低级"):
            level_prefix = "低级"
            search_name = search_name[2:]
        elif search_name.startswith("中级"):
            level_prefix = "中级"
            search_name = search_name[2:]
        
        # 检查是否是支持的系列
        for series in self.IMPLANT_SERIES.keys():
            if search_name == series:
                return True, series, level_prefix
        
        return False, None, None

    def get_price_by_type_id(self, type_id: int, region_id: int = None) -> Tuple[Optional[float], Optional[float]]:
        if region_id is None:
            region_id = self.REGION_ID_FORGE
        
        check_system = (region_id == self.REGION_ID_FORGE)
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
                if check_system and order.get("system_id") != self.SYSTEM_ID_JITA:
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

    def get_price_by_name(self, name: str, quantity: int = 1, region_id: int = None) -> Tuple[Optional[int], Optional[float], Optional[float], Optional[List[Tuple[int, str]]]]:
        if region_id is None and name.lower() == "plex":
            region_id = self.REGION_ID_PLEX_GLOBAL
            if quantity == 1:
                quantity = self.PLEX_DEFAULT_QUANTITY
        
        type_id, fuzzy_results = self.get_type_id_by_name(name)
        if not type_id:
            return None, None, None, fuzzy_results
        
        unit_sell, unit_buy = self.get_price_by_type_id(type_id, region_id)
        total_sell = unit_sell * quantity if unit_sell else None
        total_buy = unit_buy * quantity if unit_buy else None
        
        return type_id, total_sell, total_buy, fuzzy_results

    def get_implant_slot(self, name: str) -> str:
        """根据脑插名称判断插槽位置"""
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
    
    async def query_implant_series(self, series_name: str, level_prefix: str, event) -> str:
        """批量查询脑插系列价格，返回格式化的消息"""
        grades = self.IMPLANT_SERIES[series_name]
        results = []
        
        for grade in grades:
            if level_prefix:
                full_name = f"{level_prefix}{series_name}-{grade}"
            else:
                full_name = f"{series_name}-{grade}"
            
            type_id, total_sell, total_buy, fuzzy = self.get_price_by_name(full_name)
            
            if type_id and total_sell:
                results.append({
                    "grade": grade.replace("型", ""),
                    "full_grade": grade,
                    "name": full_name,
                    "sell": total_sell,
                    "buy": total_buy,
                    "type_id": type_id
                })
            else:
                results.append({
                    "grade": grade.replace("型", ""),
                    "full_grade": grade,
                    "name": full_name,
                    "sell": None,
                    "buy": None,
                    "type_id": None
                })
            
            await asyncio.sleep(0.3)
        
        # 构建输出消息
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
        
        # 添加套装效果说明
        if level_prefix == "低级":
            output_lines.extend([
                "",
                "📦 **套装效果**: 低级系列 6件套 +25% 次要效果"
            ])
        elif level_prefix == "中级":
            output_lines.extend([
                "",
                "📦 **套装效果**: 中级系列 6件套 +50% 次要效果"
            ])
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
        """查询 Jita 市场价格，支持普通物品、PLEX、脑插系列和单个脑插"""
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
                "  .jita [脑插完整名称]    - 查询单个脑插\n\n"
                "📖 **示例**:\n"
                "  .jita Tritanium\n"
                "  .jita PLEX x1000\n"
                "  .jita 圣光              # 批量查询圣光系列\n"
                "  .jita 低级圣光          # 批量查询低级圣光\n"
                "  .jita 圣光-阿尔法型     # 查询单个脑插\n"
                "  .jita 九头蛇-欧米伽型\n\n"
                "💡 其他命令: .brainlist 查看支持系列 | .help 更多帮助"
            )
            return
        
        # 解析输入
        item_name, quantity, level_prefix = self.parse_query_input(content_message)
        
        # 检查是否是脑插系列批量查询
        is_series, series_name, detected_level = self.is_implant_series_query(item_name)
        
        # 如果检测到系列查询（且没有数量参数，或者数量为1）
        if is_series and quantity == 1:
            # 使用检测到的级别前缀，如果没有则使用解析出的
            final_level = detected_level if detected_level else level_prefix
            result = await self.query_implant_series(series_name, final_level, event)
            yield event.plain_result(result)
            return
        
        # 否则作为普通物品或单个脑插查询
        type_id, total_sell, total_buy, fuzzy_results = self.get_price_by_name(item_name, quantity)
        
        if not type_id:
            if fuzzy_results and len(fuzzy_results) > 0:
                result_msg = f"❌ 未找到「{item_name}」，找到以下相关物品：\n\n"
                for i, (tid, tname) in enumerate(fuzzy_results[:5]):
                    if tname:
                        result_msg += f"  {i+1}. {tname} (ID: {tid})\n"
                    else:
                        result_msg += f"  {i+1}. Type ID: {tid}\n"
                result_msg += "\n💡 使用 .jitaid [ID] 直接查询\n"
                result_msg += "💡 脑插批量查询: .jita [系列名]"
                yield event.plain_result(result_msg)
            else:
                yield event.plain_result(
                    f"❌ 未找到物品「{item_name}」\n\n"
                    f"💡 脑插批量查询: .jita 圣光\n"
                    f"   查看支持系列: .brainlist"
                )
            return
        
        is_plex = item_name.lower() == "plex" or type_id == self.PLEX_TYPE_ID
        
        if total_sell is None and total_buy is None:
            yield event.plain_result(f"「{item_name}」当前没有订单")
            return
        
        unit_sell = total_sell / quantity if total_sell else None
        unit_buy = total_buy / quantity if total_buy else None
        
        # 判断是否是脑插（用于显示插槽信息）
        is_implant = any(grade in item_name for grade in ["阿尔法型", "贝它型", "伽玛型", "德尔塔型", "伊普西隆型", "欧米伽型"])
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
        
        if total_sell is not None:
            result_parts.append(f"💰 最低卖价: {total_sell:,.2f} ISK")
            if quantity > 1 and unit_sell:
                result_parts.append(f"   (单价: {unit_sell:,.2f} ISK)")
        else:
            result_parts.append(f"💰 最低卖价: 无订单")
        
        if total_buy is not None:
            result_parts.append(f"💎 最高买价: {total_buy:,.2f} ISK")
            if quantity > 1 and unit_buy:
                result_parts.append(f"   (单价: {unit_buy:,.2f} ISK)")
        else:
            result_parts.append(f"💎 最高买价: 无订单")
        
        if total_sell is not None and total_buy is not None:
            spread = total_sell - total_buy
            spread_pct = (spread / total_buy) * 100
            result_parts.append(f"📊 差价: {spread:,.2f} ISK ({spread_pct:.1f}%)")
        
        # 如果是脑插，添加批量查询提示
        if is_implant:
            # 提取系列名
            for series in self.IMPLANT_SERIES.keys():
                if series in item_name:
                    result_parts.append(f"\n💡 批量查询: .jita {series}")
                    break
        
        yield event.plain_result("\n".join(result_parts))

    @filter.command(".jitaid")
    async def jita_by_id(self, event: AstrMessageEvent, type_id_str: str):
        """通过 type_id 查询价格"""
        try:
            type_id = int(type_id_str.strip())
        except ValueError:
            yield event.plain_result("❌ 请提供正确的 Type ID")
            return
        
        unit_sell, unit_buy = self.get_price_by_type_id(type_id)
        
        if unit_sell is None and unit_buy is None:
            yield event.plain_result(f"Type ID {type_id} 在 Jita 没有订单")
            return
        
        result_parts = [f"📦 **Type ID: {type_id}**"]
        
        if unit_sell is not None:
            result_parts.append(f"💰 最低卖价: {unit_sell:,.2f} ISK")
        if unit_buy is not None:
            result_parts.append(f"💎 最高买价: {unit_buy:,.2f} ISK")
        
        if unit_sell is not None and unit_buy is not None:
            spread = unit_sell - unit_buy
            spread_pct = (spread / unit_buy) * 100
            result_parts.append(f"📊 差价: {spread:,.2f} ISK ({spread_pct:.1f}%)")
        
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
            f"  .jita 九头蛇\n"
            f"  .jita 圣光-阿尔法型\n\n"
            f"💡 批量查询专用: .brain [系列名] (效果相同)"
        )

    @filter.command(".brain")
    async def brain(self, event: AstrMessageEvent, series_name: str = ""):
        """批量查询脑插系列价格（与.jita系列查询功能相同）"""
        if not series_name:
            series_list = "、".join(self.IMPLANT_SERIES.keys())
            yield event.plain_result(
                f"🧠 **脑插批量查询**\n\n"
                f"用法: .brain [系列名]\n"
                f"      .brain 低级[系列名]\n"
                f"      .brain 中级[系列名]\n\n"
                f"支持系列: {series_list}\n\n"
                f"示例: .brain 圣光\n"
                f"      .brain 低级圣光\n"
                f"      .brain 九头蛇\n\n"
                f"💡 也可以使用 .jita [系列名] 达到相同效果"
            )
            return
        
        series_name = series_name.strip()
        
        # 判断级别前缀
        level_prefix = ""
        if series_name.startswith("低级"):
            level_prefix = "低级"
            base_name = series_name[2:]
        elif series_name.startswith("中级"):
            level_prefix = "中级"
            base_name = series_name[2:]
        else:
            base_name = series_name
        
        # 查找系列
        matched_series = None
        for key in self.IMPLANT_SERIES.keys():
            if key == base_name:
                matched_series = key
                break
        
        if not matched_series:
            series_list = "、".join(self.IMPLANT_SERIES.keys())
            yield event.plain_result(
                f"❌ 未找到系列「{series_name}」\n\n"
                f"支持的系列: {series_list}\n\n"
                f"💡 使用 .brainlist 查看完整列表"
            )
            return
        
        yield event.plain_result(f"🔍 正在批量查询「{level_prefix}{matched_series}」系列价格...\n(查询6个脑插，请稍候)")
        
        result = await self.query_implant_series(matched_series, level_prefix, event)
        yield event.plain_result(result)

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
        
        result_lines = [f"🔍 搜索结果: {search_name}", ""]
        
        for i, (tid, tname) in enumerate(results[:10]):
            if tname:
                result_lines.append(f"  {i+1}. {tname} (ID: {tid})")
            else:
                result_lines.append(f"  {i+1}. Type ID: {tid}")
        
        result_lines.append("\n💡 使用 .jitaid [ID] 查询价格")
        result_lines.append("💡 脑插批量查询: .jita [系列名]")
        
        yield event.plain_result("\n".join(result_lines))

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
            "🔹 **脑插查询**\n"
            "  .jita [系列名]          - 批量查询全套脑插\n"
            "  .jita 低级[系列名]      - 查询低级系列\n"
            "  .jita 中级[系列名]      - 查询中级系列\n"
            "  .jita [名称]-[级别]     - 查询单个脑插\n"
            "  .brain [系列名]         - 批量查询（同上）\n"
            "  .brainlist              - 查看支持系列\n\n"
            "🔹 **搜索**\n"
            "  .search [名称]          - 模糊搜索物品\n\n"
            "📖 **示例**:\n"
            "  .jita Tritanium\n"
            "  .jita PLEX x1000\n"
            "  .jita 圣光              # 批量查询圣光系列\n"
            "  .jita 低级圣光          # 批量查询低级圣光\n"
            "  .jita 圣光-阿尔法型     # 查询单个脑插\n"
            "  .brain 九头蛇           # 批量查询\n"
            "  .brainlist              # 查看支持系列"
        )
