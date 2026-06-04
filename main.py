from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import requests
import re
from typing import Optional, Tuple, List

@register("EveMarket", "YourName", "EVE Online Jita 市场查询插件", "1.0.0")
class EveMarketPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    REGION_ID_FORGE = 10000002
    SYSTEM_ID_JITA = 30000142
    ESI_BASE = "https://esi.evetech.net/latest"
    
    # 中文到英文的常见物品映射
    CN_TO_EN = {
        "三钛合金": "Tritanium",
        "类晶体胶矿": "Mexallon",
        "类银超金属": "Pyerite", 
        "同位聚合体": "Isogen",
        "超新星诺克石": "Nocxium",
        "晶状石英核岩": "Megacyte",
        "超噬矿": "Zydrine",
        "伊甸币": "Plex",
        "狂怒者级": "Vexor",
        "刺客级": "Stiletto",
        "裂谷级": "Rifter",
        "主宰级": "Dominix",
        "灾难级": "Apocalypse",
        "乌鸦级": "Raven",
        "幼龙级": "Drake",
        "毒蜥级": "Gila",
        "伊什塔级": "Ishtar",
        "夜魔侠级": "Daredevil",
        # 矿物
        "莫尔石": "Morphite",
        # 脑插系列
        "圣光": "Saint",
        "护符": "Talisman",
        "水晶": "Crystal",
        "蝰蛇": "Viper",
        "强势": "Potent",
        "九头蛇": "Hydra",
        "阿斯克雷": "Asklepian",
    }

    async def initialize(self):
        logger.info("EVE Market 插件已加载")

    async def terminate(self):
        logger.info("EVE Market 插件已卸载")

    # ==================== 搜索功能 ====================
    
    def get_type_id(self, name: str) -> Optional[int]:
        """获取物品 Type ID"""
        try:
            url = "https://www.fuzzwork.co.uk/api/typeid.php"
            r = requests.get(url, params={"typename": name}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    return data[0].get("typeID")
                elif isinstance(data, dict) and "typeID" in data:
                    return data["typeID"]
        except Exception as e:
            logger.error(f"查询失败: {e}")
        return None

    def search_fuzzy(self, keyword: str) -> List[Tuple[int, str]]:
        """模糊搜索物品"""
        try:
            url = f"{self.ESI_BASE}/universe/ids/"
            headers = {"Accept-Language": "zh"}
            resp = requests.post(url, headers=headers, json=[keyword], timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("inventory_types", []):
                    results.append((item.get("id"), item.get("name")))
                return results
        except Exception as e:
            logger.error(f"搜索失败: {e}")
        return []

    def smart_search(self, keyword: str) -> Tuple[Optional[int], Optional[str], List[Tuple[int, str]]]:
        """智能搜索：支持中文、英文、模糊匹配"""
        keyword = keyword.strip()
        
        # 1. 检查中文映射表
        if keyword in self.CN_TO_EN:
            en_name = self.CN_TO_EN[keyword]
            type_id = self.get_type_id(en_name)
            if type_id:
                return type_id, en_name, []
        
        # 2. 脑插特殊处理
        if keyword in ["圣光", "护符", "水晶", "蝰蛇", "强势", "九头蛇", "阿斯克雷"]:
            en_name = self.CN_TO_EN[keyword]
            # 尝试查询阿尔法型作为代表
            test_name = f"'{en_name}' Alpha"
            type_id = self.get_type_id(test_name)
            if type_id:
                return type_id, f"{keyword}系列", []
        
        # 3. 直接搜索
        type_id = self.get_type_id(keyword)
        if type_id:
            return type_id, keyword, []
        
        # 4. 尝试中英文组合
        for cn, en in self.CN_TO_EN.items():
            if cn in keyword or keyword in cn:
                type_id = self.get_type_id(en)
                if type_id:
                    return type_id, en, []
        
        # 5. 模糊搜索
        results = self.search_fuzzy(keyword)
        if results:
            return results[0][0], results[0][1], results
        
        return None, None, []

    def get_price(self, type_id: int) -> Tuple[Optional[float], Optional[float]]:
        """获取 Jita 市场价格"""
        sell_prices = []
        buy_prices = []
        page = 1
        
        while True:
            url = f"{self.ESI_BASE}/markets/{self.REGION_ID_FORGE}/orders/"
            params = {"page": page, "type_id": type_id}
            
            try:
                resp = requests.get(url, params=params, timeout=15)
                if resp.status_code != 200:
                    break
                    
                orders = resp.json()
                if not orders:
                    break
                
                for order in orders:
                    if order.get("system_id") != self.SYSTEM_ID_JITA:
                        continue
                    
                    price = order["price"]
                    if order["is_buy_order"]:
                        buy_prices.append(price)
                    else:
                        sell_prices.append(price)
                
                if "X-Pages" in resp.headers:
                    total_pages = int(resp.headers["X-Pages"])
                    if page >= total_pages:
                        break
                page += 1
                
            except Exception as e:
                logger.error(f"获取订单失败: {e}")
                break
        
        min_sell = min(sell_prices) if sell_prices else None
        max_buy = max(buy_prices) if buy_prices else None
        return min_sell, max_buy

    def parse_quantity(self, input_str: str) -> Tuple[str, int]:
        """解析物品名称和数量"""
        input_str = input_str.strip()
        
        # 格式: 物品名 x100
        match = re.match(r'^(.+?)\s*[×x*]\s*(\d+)$', input_str, re.IGNORECASE)
        if match:
            return match.group(1).strip(), int(match.group(2))
        
        # 格式: 100x 物品名
        match = re.match(r'^(\d+)\s*[×x*]\s*(.+?)$', input_str, re.IGNORECASE)
        if match:
            return match.group(2).strip(), int(match.group(1))
        
        # 格式: 100 物品名
        match = re.match(r'^(\d+)\s+(.+?)$', input_str)
        if match:
            return match.group(2).strip(), int(match.group(1))
        
        return input_str, 1

    # ==================== 主命令 ====================
    
    @filter.command(".jita")
    async def jita(self, event: AstrMessageEvent, content: str = ""):
        """查询 Jita 市场价格（支持中文和数量）
        
        用法: .jita [物品名]
              .jita [物品名] x[数量]
              .jita [数量] [物品名]
        
        示例:
            .jita 三钛合金
            .jita 狂怒者级
            .jita PLEX x100
            .jita 100 三钛合金
            .jita 圣光
        """
        if not content:
            yield event.plain_result(
                "📋 **Jita 市场查询**\n\n"
                "用法: .jita [物品名]\n"
                "      .jita [物品名] x[数量]\n\n"
                "📖 示例:\n"
                "  .jita 三钛合金\n"
                "  .jita 狂怒者级\n"
                "  .jita PLEX x100\n"
                "  .jita 100 三钛合金\n"
                "  .jita 圣光\n\n"
                "💡 支持中英文名称，支持数量计算"
            )
            return
        
        # 解析数量
        item_name, quantity = self.parse_quantity(content)
        
        if not item_name:
            yield event.plain_result("❌ 请提供物品名称")
            return
        
        yield event.plain_result(f"🔍 正在查询「{item_name}」...")
        
        # 智能搜索
        type_id, actual_name, suggestions = self.smart_search(item_name)
        
        if not type_id:
            if suggestions:
                msg = f"❌ 未找到「{item_name}」，相关物品：\n\n"
                for tid, tname in suggestions[:5]:
                    msg += f"  • {tname}\n"
                    msg += f"    查询: .jitaid {tid}\n\n"
                msg += "💡 使用更完整的名称重试"
                yield event.plain_result(msg)
            else:
                yield event.plain_result(
                    f"❌ 未找到「{item_name}」\n\n"
                    f"💡 尝试:\n"
                    f"  - 使用英文名称: .jita Tritanium\n"
                    f"  - 使用常见中文名: .jita 三钛合金\n"
                    f"  - 舰船示例: .jita 狂怒者级"
                )
            return
        
        # 获取价格
        sell, buy = self.get_price(type_id)
        
        if sell is None and buy is None:
            yield event.plain_result(f"「{actual_name}」在 Jita 没有公开订单")
            return
        
        # 计算总价
        total_sell = sell * quantity if sell else None
        total_buy = buy * quantity if buy else None
        
        # 构建返回消息
        result_parts = [
            "📍 **Jita 市场**",
            f"📦 **{actual_name}**" + (f" x {quantity}" if quantity > 1 else ""),
            "",
        ]
        
        if total_sell:
            result_parts.append(f"💰 最低卖价: {total_sell:,.2f} ISK")
            if quantity > 1 and sell:
                result_parts.append(f"   (单价: {sell:,.2f} ISK)")
        else:
            result_parts.append(f"💰 最低卖价: 无订单")
        
        if total_buy:
            result_parts.append(f"💎 最高买价: {total_buy:,.2f} ISK")
            if quantity > 1 and buy:
                result_parts.append(f"   (单价: {buy:,.2f} ISK)")
        else:
            result_parts.append(f"💎 最高买价: 无订单")
        
        if sell and buy:
            spread = sell - buy
            spread_pct = (spread / buy) * 100
            result_parts.append(f"📊 买卖差价: {spread:,.2f} ISK ({spread_pct:.1f}%)")
        
        yield event.plain_result("\n".join(result_parts))

    @filter.command(".jitaid")
    async def jita_by_id(self, event: AstrMessageEvent, type_id_str: str):
        """通过 Type ID 查询价格
        
        用法: .jitaid [TypeID]
        示例: .jitaid 34
        """
        try:
            type_id = int(type_id_str.strip())
        except ValueError:
            yield event.plain_result("❌ 请提供正确的 Type ID 数字")
            return
        
        sell, buy = self.get_price(type_id)
        
        if sell is None and buy is None:
            yield event.plain_result(f"Type ID {type_id} 在 Jita 没有订单")
            return
        
        result_parts = [
            "📍 **Jita 市场**",
            f"📦 **Type ID: {type_id}**",
            "",
        ]
        
        if sell:
            result_parts.append(f"💰 最低卖价: {sell:,.2f} ISK")
        if buy:
            result_parts.append(f"💎 最高买价: {buy:,.2f} ISK")
        
        if sell and buy:
            spread = sell - buy
            spread_pct = (spread / buy) * 100
            result_parts.append(f"📊 买卖差价: {spread:,.2f} ISK ({spread_pct:.1f}%)")
        
        yield event.plain_result("\n".join(result_parts))
