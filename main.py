from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import requests
import re
from typing import Optional, Tuple

@register("CJ6MTMarket", "YourName", "C-J6MT 星系市场查询插件", "1.0.0")
class CJ6MTMarketPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    # C-J6MT 星系配置
    SYSTEM_ID = 30000772          # C-J6MT 星系ID
    REGION_ID = 10000023          # 因斯姆尔星域ID
    ESI_BASE = "https://esi.evetech.net/latest"
    
    # Jita 对比数据
    JITA_SYSTEM_ID = 30000142
    JITA_REGION_ID = 10000002

    async def initialize(self):
        logger.info("C-J6MT 市场插件已加载")

    async def terminate(self):
        logger.info("C-J6MT 市场插件已卸载")

    # ==================== 查询方法 ====================
    
    def get_type_id(self, name: str) -> Optional[int]:
        """获取物品 Type ID"""
        # 方法1: fuzzwork API
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
            logger.error(f"fuzzwork查询失败: {e}")
        
        # 方法2: ESI API
        try:
            url = f"{self.ESI_BASE}/universe/ids/"
            resp = requests.post(url, headers={"Accept-Language": "zh"}, json=[name], timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                inv_types = data.get("inventory_types", [])
                if inv_types:
                    return inv_types[0].get("id")
        except Exception as e:
            logger.error(f"ESI查询失败: {e}")
        
        return None

    def get_market_orders(self, type_id: int, region_id: int, system_id: int = None) -> Tuple[Optional[float], Optional[float]]:
        """获取市场订单价格"""
        sell_prices = []
        buy_prices = []
        page = 1
        
        while True:
            url = f"{self.ESI_BASE}/markets/{region_id}/orders/"
            params = {"page": page, "type_id": type_id}
            
            try:
                resp = requests.get(url, params=params, timeout=15)
                if resp.status_code != 200:
                    break
                    
                orders = resp.json()
                if not orders:
                    break
                
                for order in orders:
                    # 如果指定了星系ID，只取该星系的订单
                    if system_id and order.get("system_id") != system_id:
                        continue
                    
                    price = order["price"]
                    if order["is_buy_order"]:
                        buy_prices.append(price)
                    else:
                        sell_prices.append(price)
                
                # 检查是否有下一页
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

    def parse_input(self, input_str: str) -> Tuple[str, int]:
        """解析物品名称和数量"""
        input_str = input_str.strip()
        
        # 格式: 物品名 x数量
        match = re.match(r'^(.+?)\s*[×x*]\s*(\d+)$', input_str, re.IGNORECASE)
        if match:
            return match.group(1).strip(), int(match.group(2))
        
        # 格式: 数量x物品名
        match = re.match(r'^(\d+)\s*[×x*]\s*(.+?)$', input_str, re.IGNORECASE)
        if match:
            return match.group(2).strip(), int(match.group(1))
        
        # 格式: 数量 物品名
        match = re.match(r'^(\d+)\s+(.+?)$', input_str)
        if match:
            return match.group(2).strip(), int(match.group(1))
        
        return input_str, 1

    # ==================== 主命令 ====================
    
    @filter.command(".c")
    async def query_cj6mt(self, event: AstrMessageEvent, content: str = ""):
        """查询 C-J6MT 星系市场价格
        
        用法:
            .c [物品名]          - 查询单个物品
            .c [物品名] x[数量]  - 查询多个数量
            .c [数量] [物品名]   - 查询多个数量
        
        示例:
            .c Tritanium
            .c PLEX x100
            .c 100 Vexor
        """
        if not content:
            yield event.plain_result(
                "🚀 **C-J6MT 市场查询**\n\n"
                "用法: .c [物品名]\n"
                "      .c [物品名] x[数量]\n\n"
                "📖 示例:\n"
                "  .c Tritanium\n"
                "  .c PLEX\n"
                "  .c Vexor x10\n"
                "  .c 100 PLEX\n\n"
                "💡 支持中英文物品名称"
            )
            return
        
        # 解析输入
        item_name, quantity = self.parse_input(content)
        
        if not item_name:
            yield event.plain_result("❌ 请提供物品名称")
            return
        
        yield event.plain_result(f"🔍 正在查询 C-J6MT 市场的 {item_name}...")
        
        # 获取物品 ID
        type_id = self.get_type_id(item_name)
        if not type_id:
            yield event.plain_result(f"❌ 未找到物品「{item_name}」\n\n💡 尝试使用英文名称，如: .c Tritanium")
            return
        
        # 获取 C-J6MT 价格
        cj6mt_sell, cj6mt_buy = self.get_market_orders(type_id, self.REGION_ID, self.SYSTEM_ID)
        
        # 获取 Jita 价格作为对比
        jita_sell, jita_buy = self.get_market_orders(type_id, self.JITA_REGION_ID, self.JITA_SYSTEM_ID)
        
        # 计算总价
        total_sell = cj6mt_sell * quantity if cj6mt_sell else None
        total_buy = cj6mt_buy * quantity if cj6mt_buy else None
        jita_total_sell = jita_sell * quantity if jita_sell else None
        
        # 构建返回消息
        result_parts = [
            "🚀 **C-J6MT 市场**",
            f"📍 星系: C-J6MT | 🌌 星域: 因斯姆尔",
            "",
            f"📦 **{item_name}**" + (f" x {quantity}" if quantity > 1 else ""),
            "",
        ]
        
        # C-J6MT 价格
        if total_sell:
            result_parts.append(f"💰 最低卖价: {total_sell:,.2f} ISK")
            if quantity > 1 and cj6mt_sell:
                result_parts.append(f"   (单价: {cj6mt_sell:,.2f} ISK)")
        else:
            result_parts.append(f"💰 最低卖价: 无公开订单")
        
        if total_buy:
            result_parts.append(f"💎 最高买价: {total_buy:,.2f} ISK")
            if quantity > 1 and cj6mt_buy:
                result_parts.append(f"   (单价: {cj6mt_buy:,.2f} ISK)")
        else:
            result_parts.append(f"💎 最高买价: 无公开订单")
        
        # 买卖差价
        if cj6mt_sell and cj6mt_buy:
            spread = cj6mt_sell - cj6mt_buy
            spread_pct = (spread / cj6mt_buy) * 100
            result_parts.append(f"📊 买卖差价: {spread:,.2f} ISK ({spread_pct:.1f}%)")
        
        # Jita 对比
        if jita_total_sell and total_sell:
            premium = (total_sell - jita_total_sell) / jita_total_sell * 100
            result_parts.extend([
                "",
                f"📊 **与 Jita 对比**",
                f"   Jita 卖价: {jita_total_sell:,.2f} ISK",
                f"   C-J6MT 溢价: +{premium:.1f}%"
            ])
        elif jita_total_sell and not total_sell:
            result_parts.extend([
                "",
                f"📊 **与 Jita 对比**",
                f"   Jita 卖价: {jita_total_sell:,.2f} ISK",
                f"   C-J6MT: 无订单"
            ])
        
        # 套利提示
        if jita_buy and cj6mt_sell:
            arbitrage = jita_buy * quantity - cj6mt_sell * quantity
            if arbitrage > 0:
                result_parts.extend([
                    "",
                    f"💹 **套利机会**",
                    f"   从 C-J6MT 买入: {cj6mt_sell * quantity:,.2f} ISK",
                    f"   卖到 Jita: {jita_buy * quantity:,.2f} ISK",
                    f"   利润: +{arbitrage:,.2f} ISK"
                ])
        
        result_parts.append("")
        result_parts.append("💡 提示: 00星系价格通常比 Jita 高 10-30%")
        
        yield event.plain_result("\n".join(result_parts))

    @filter.command(".chelp")
    async def help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        yield event.plain_result(
            "🚀 **C-J6MT 市场查询插件**\n\n"
            "📋 命令:\n"
            "  .c [物品名]          - 查询物品价格\n"
            "  .c [物品名] x[数量]  - 查询多个数量\n"
            "  .c [数量] [物品名]   - 查询多个数量\n"
            "  .chelp               - 显示帮助\n\n"
            "📖 示例:\n"
            "  .c Tritanium\n"
            "  .c PLEX\n"
            "  .c Vexor\n"
            "  .c PLEX x100\n"
            "  .c 10 Vexor\n\n"
            "📍 市场信息:\n"
            "  星系: C-J6MT\n"
            "  星域: 因斯姆尔 (Insmother)\n"
            "  类型: 00 星系\n\n"
            "⚠️ 注意: 00星系价格通常比 Jita 高 10-30%"
        )
