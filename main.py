import aiohttp
import json
import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 欧服 ESI API 基础地址
ESI_BASE_URL = "https://esi.evetech.net/latest"

# 常用贸易中心（市场枢纽）的 Region ID 和中文名映射
# 来源: ESI /universe/regions/ 接口
TRADE_HUBS = {
    "吉他": 10000002,      # The Forge (Jita)
    "多迪谢": 10000001,    # Domain (Amarr)
    "俄萨": 10000043,      # Metropolis (Hek)
    "勒金斯": 10000032,    # Sinq Laison (Rens)
    "艾玛": 10000001,      # Domain (Amarr 同区域)
    "伊甸": 10000068,      # The Citadel (Perimeter/TTT)
}

# 部分常用物品的名称->type_id 映射（便于演示，实际应用中可扩展为数据库或 ESI 搜索）
# 完整实现建议使用 ESI /universe/types/ 接口的 /universe/ids/ 或 /universe/search/
COMMON_ITEMS = {
    "plex": 29668,          # PLEX
    "注射器": 40540,        # Large Skill Injector
    "伊甸币": 47479,        # Edencom Survey Data (简化)
}


class EveMarketPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.session: Optional[aiohttp.ClientSession] = None
        # 结果缓存（简单内存缓存，生产环境建议使用持久化）
        self.cache: Dict[str, Tuple[Dict, float]] = {}
        self.cache_ttl = 60  # 缓存 60 秒

    async def get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "AstrBot EVE Market Plugin/1.0 (Contact: Your@email.com)"
                }
            )
        return self.session

    async def close_session(self):
        """关闭 aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def search_type_id(self, item_name: str) -> Optional[int]:
        """
        通过 ESI 搜索物品 ID
        GET /universe/search/?search={name}&categories=inventory_type
        """
        try:
            session = await self.get_session()
            url = f"{ESI_BASE_URL}/universe/search/"
            params = {
                "search": item_name,
                "categories": "inventory_type",
                "strict": "true",
                "language": "zh"
            }
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("inventory_type") and len(data["inventory_type"]) > 0:
                        return data["inventory_type"][0]
                elif resp.status == 404:
                    logger.warning(f"物品 '{item_name}' 未找到")
                else:
                    logger.error(f"搜索物品失败: {resp.status}")
        except Exception as e:
            logger.error(f"搜索物品异常: {e}")
        return None

    async def get_region_orders(self, region_id: int, type_id: int) -> Optional[Dict]:
        """
        获取指定区域、指定物品的市场订单
        GET /markets/{region_id}/orders/?order_type=all&type_id={type_id}
        返回数据包含 buy 和 sell 两个数组
        """
        cache_key = f"{region_id}_{type_id}"
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if (datetime.now().timestamp() - timestamp) < self.cache_ttl:
                logger.debug(f"使用缓存 {cache_key}")
                return data
        
        try:
            session = await self.get_session()
            url = f"{ESI_BASE_URL}/markets/{region_id}/orders/"
            params = {
                "order_type": "all",
                "type_id": type_id
            }
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    orders = await resp.json()
                    # 分离买单和卖单
                    buy_orders = [o for o in orders if o["is_buy_order"]]
                    sell_orders = [o for o in orders if not o["is_buy_order"]]
                    
                    # 最优买价（最高买入价，即玩家愿意出的最高价）
                    best_buy = max(buy_orders, key=lambda x: x["price"]) if buy_orders else None
                    # 最优卖价（最低卖出价）
                    best_sell = min(sell_orders, key=lambda x: x["price"]) if sell_orders else None
                    
                    result = {
                        "buy": best_buy,
                        "sell": best_sell,
                        "total_buy_volume": sum(o["volume_remain"] for o in buy_orders),
                        "total_sell_volume": sum(o["volume_remain"] for o in sell_orders),
                        "buy_count": len(buy_orders),
                        "sell_count": len(sell_orders),
                        "region_id": region_id,
                        "type_id": type_id
                    }
                    self.cache[cache_key] = (result, datetime.now().timestamp())
                    return result
                else:
                    logger.error(f"获取订单失败: {resp.status} - {await resp.text()}")
        except Exception as e:
            logger.error(f"获取订单异常: {e}")
        return None

    def format_price(self, price: float) -> str:
        """格式化价格显示"""
        return f"{price:,.2f} ISK"

    def format_result(self, item_name: str, hub_name: str, data: Dict, type_id: int) -> str:
        """格式化输出结果"""
        best_sell = data.get("sell")
        best_buy = data.get("buy")
        
        lines = [
            f"📊 **{item_name}** 市场行情",
            f"📍 {hub_name} (Region ID: {data['region_id']}, Type ID: {type_id})",
            f"⏰ 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "--- 卖单 (卖家挂单) ---"
        ]
        
        if best_sell:
            lines.append(f"💰 最低卖价: {self.format_price(best_sell['price'])}")
            lines.append(f"📦 订单数量: {data['sell_count']} 个")
            lines.append(f"📦 剩余总量: {self.format_price(data['total_sell_volume'])} 单位")
            lines.append(f"🏢 所在星系: {best_sell.get('location_id', 'N/A')}")
        else:
            lines.append("❌ 暂无卖单")
        
        lines.append("")
        lines.append("--- 买单 (玩家收单) ---")
        
        if best_buy:
            lines.append(f"💰 最高买价: {self.format_price(best_buy['price'])}")
            lines.append(f"📦 订单数量: {data['buy_count']} 个")
            lines.append(f"📦 剩余总量: {self.format_price(data['total_buy_volume'])} 单位")
            lines.append(f"🏢 所在星系: {best_buy.get('location_id', 'N/A')}")
        else:
            lines.append("❌ 暂无买单")
        
        # 如果有买卖双方，计算差价和利润率
        if best_sell and best_buy:
            spread = best_sell["price"] - best_buy["price"]
            profit_margin = (spread / best_buy["price"]) * 100 if best_buy["price"] > 0 else 0
            lines.append("")
            lines.append("--- 套利分析 ---")
            lines.append(f"📈 买卖差价: {self.format_price(spread)}")
            lines.append(f"📊 利润率: {profit_margin:.2f}%")
            lines.append("")
            lines.append("*注：以上未计入税费和经纪费，实际利润会略低。*")
        
        return "\n".join(lines)

    @filter.command("eveprice")
    async def eveprice(self, event: AstrMessageEvent):
        """
        查询 EVE 欧服物品价格
        用法: /eveprice <物品名称> [贸易中心]
        示例: /eveprice 帕拉丁级
              /eveprice 注射器 吉他
        """
        # 解析命令参数
        message = event.message_str.strip()
        parts = message.split(maxsplit=2)
        
        if len(parts) < 2:
            yield event.plain_result(
                "❌ 用法错误！\n"
                "正确用法:\n"
                "/eveprice <物品名称> [贸易中心]\n"
                "示例:\n"
                "/eveprice 帕拉丁级\n"
                "/eveprice 注射器 吉他\n\n"
                "支持的贸易中心: " + ", ".join(TRADE_HUBS.keys())
            )
            return
        
        # 获取物品名称和贸易中心
        item_name = parts[1]
        hub_name = parts[2] if len(parts) > 2 else "吉他"
        
        # 检查贸易中心是否存在
        if hub_name not in TRADE_HUBS:
            yield event.plain_result(
                f"❌ 未知贸易中心: {hub_name}\n"
                f"支持的贸易中心: {', '.join(TRADE_HUBS.keys())}"
            )
            return
        
        region_id = TRADE_HUBS[hub_name]
        
        # 先发送一个"正在查询"的提示（可选，命令太长时有用）
        yield event.plain_result(f"🔍 正在查询 {item_name} 在 {hub_name} 的市场行情...")
        
        # 获取物品 ID
        type_id = None
        
        # 先检查常用物品映射
        item_lower = item_name.lower()
        if item_lower in COMMON_ITEMS:
            type_id = COMMON_ITEMS[item_lower]
            logger.info(f"从映射中找到物品: {item_name} -> {type_id}")
        else:
            # 调用 ESI 搜索
            type_id = await self.search_type_id(item_name)
            if not type_id:
                # 尝试模糊匹配（去掉空格、中文简繁等简单处理）
                yield event.plain_result(f"❌ 未找到物品: {item_name}\n请检查物品名称是否正确，或尝试使用英文名。")
                return
        
        # 获取市场订单
        market_data = await self.get_region_orders(region_id, type_id)
        if not market_data:
            yield event.plain_result(f"❌ 获取市场数据失败，请稍后重试。\n物品: {item_name} ({type_id})")
            return
        
        # 格式化输出
        result_text = self.format_result(item_name, hub_name, market_data, type_id)
        yield event.plain_result(result_text)

    @filter.command("evehubs")
    async def evehubs(self, event: AstrMessageEvent):
        """显示支持的贸易中心列表"""
        hub_list = "\n".join([f"  • {name} (Region ID: {rid})" for name, rid in TRADE_HUBS.items()])
        yield event.plain_result(
            "🌟 **EVE Online 欧服贸易中心列表** 🌟\n\n"
            f"{hub_list}\n\n"
            "使用示例: `/eveprice 帕拉丁级 吉他`\n"
            "不指定贸易中心时默认使用吉他 (Jita)。"
        )

    @filter.command("eveitemid")
    async def eveitemid(self, event: AstrMessageEvent):
        """
        查询物品的 Type ID
        用法: /eveitemid <物品名称>
        """
        message = event.message_str.strip()
        parts = message.split(maxsplit=1)
        
        if len(parts) < 2:
            yield event.plain_result("❌ 用法: /eveitemid <物品名称>")
            return
        
        item_name = parts[1]
        
        yield event.plain_result(f"🔍 正在搜索物品: {item_name}...")
        
        type_id = await self.search_type_id(item_name)
        if type_id:
            yield event.plain_result(f"✅ 物品: {item_name}\n📦 Type ID: {type_id}\n\n可使用 `/eveprice {item_name}` 查询价格。")
        else:
            yield event.plain_result(f"❌ 未找到物品: {item_name}\n请检查名称或尝试英文名。")

    async def terminate(self):
        """插件卸载时调用，关闭网络连接"""
        await self.close_session()
        logger.info("EVE Market 插件已卸载")


# 插件注册（元数据）
def register_plugin(context: Context):
    """AstrBot 插件入口"""
    return EveMarketPlugin(context)
