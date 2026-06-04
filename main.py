from typing import Optional, Dict, Any, Tuple
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
import aiohttp

# 贸易中心星系ID (欧服常见)
TRADE_HUBS = {
    "jita": {"id": 30000142, "name": "Jita"},
    "amarr": {"id": 30002187, "name": "Amarr"},
    "dodixie": {"id": 30002659, "name": "Dodixie"},
    "rens": {"id": 30002510, "name": "Rens"},
    "hek": {"id": 30002053, "name": "Hek"},
}

# API 端点
FUZZWORK_TYPE_ID = "https://www.fuzzwork.co.uk/api/typeid.php?typename={name}"
MARKET_API = "https://eve-marketer.com/api/v1/market/{type_id}/{region_id}"


class EveMarketPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        logger.info("EVE市场插件已初始化")
    
    @filter.command("market")
    async def query_market(self, event: AstrMessageEvent):
        """用法: /market <物品名> [贸易中心]
        示例: /market Plex jita
        """
        input_text = event.message_str.strip()
        parts = input_text.split()
        
        if len(parts) < 2:
            yield event.plain_result("用法: /market <物品名> [贸易中心]\n默认贸易中心: Jita\n示例: /market Plex jita")
            return
        
        # 解析物品名和贸易中心（支持带空格的物品名）
        if len(parts) > 2 and parts[2].lower() in TRADE_HUBS:
            item_name = parts[1]
            hub_key = parts[2].lower()
        else:
            hub_index = None
            for i, part in enumerate(parts[1:], 1):
                if part.lower() in TRADE_HUBS:
                    hub_index = i
                    break
            if hub_index:
                item_name = ' '.join(parts[1:hub_index])
                hub_key = parts[hub_index].lower()
            else:
                item_name = ' '.join(parts[1:])
                hub_key = "jita"
        
        if hub_key not in TRADE_HUBS:
            hub_names = ", ".join(TRADE_HUBS.keys())
            yield event.plain_result(f"不支持的贸易中心: {hub_key}\n支持: {hub_names}")
            return
        
        hub = TRADE_HUBS[hub_key]
        
        yield event.plain_result(f"正在查询 {item_name} 在 {hub['name']} 的价格...")
        
        # 搜索物品
        type_id, matched_name = await self._search_item(item_name)
        if not type_id:
            yield event.plain_result(f"未找到物品: {item_name}\n提示：请尝试使用英文名称")
            return
        
        # 获取市场数据
        market_data = await self._get_market_data(type_id, hub['id'])
        if not market_data:
            yield event.plain_result(f"无法获取 {matched_name} 的市场数据")
            return
        
        # 格式化输出
        result = self._format_result(matched_name, hub['name'], market_data)
        yield event.plain_result(result)
    
    @filter.command("markets")
    async def list_hubs(self, event: AstrMessageEvent):
        """列出所有支持的贸易中心"""
        hubs = "\n".join([f"• {v['name']} ({k})" for k, v in TRADE_HUBS.items()])
        yield event.plain_result(f"支持的贸易中心:\n{hubs}\n\n示例: /market Plex jita")
    
    @filter.command("search")
    async def search_item(self, event: AstrMessageEvent):
        """搜索物品ID: /search <物品名>"""
        parts = event.message_str.strip().split()
        if len(parts) < 2:
            yield event.plain_result("用法: /search <物品名>\n示例: /search Plex")
            return
        
        item_name = ' '.join(parts[1:])
        yield event.plain_result(f"正在搜索: {item_name}...")
        
        type_id, matched_name = await self._search_item(item_name)
        if type_id:
            yield event.plain_result(f"✅ 找到物品: {matched_name}\nType ID: {type_id}")
        else:
            yield event.plain_result(f"❌ 未找到物品: {item_name}")
    
    async def _search_item(self, name: str) -> Tuple[Optional[int], Optional[str]]:
        """使用 fuzzwork API 搜索物品"""
        try:
            url = FUZZWORK_TYPE_ID.format(name=name)
            headers = {
                "User-Agent": "AstrBot-EVE-Market-Plugin/1.0",
                "Accept": "application/json"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"fuzzwork 返回: {data}")
                        if isinstance(data, dict) and "typeID" in data:
                            return data["typeID"], data.get("typeName", name)
            return None, None
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return None, None
    
    async def _get_market_data(self, type_id: int, region_id: int) -> Optional[Dict[str, Any]]:
        """获取市场订单数据"""
        try:
            url = MARKET_API.format(type_id=type_id, region_id=region_id)
            headers = {"User-Agent": "AstrBot-EVE-Market-Plugin/1.0"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "buy_max": data.get("buy", {}).get("max", 0),
                            "sell_min": data.get("sell", {}).get("min", 0),
                        }
            return None
        except Exception as e:
            logger.error(f"获取市场数据失败: {e}")
            return None
    
    def _format_result(self, item_name: str, hub_name: str, data: Dict) -> str:
        """格式化输出"""
        buy_max = data.get("buy_max", 0)
        sell_min = data.get("sell_min", 0)
        
        buy_str = f"{buy_max:,.2f}" if buy_max > 0 else "暂无买盘"
        sell_str = f"{sell_min:,.2f}" if sell_min > 0 else "暂无卖盘"
        
        spread_info = ""
        if buy_max > 0 and sell_min > 0 and sell_min > buy_max:
            spread = sell_min - buy_max
            profit_pct = (spread / buy_max) * 100
            spread_info = f"\n📊 **差价**: {spread:,.2f} ISK ({profit_pct:.1f}%)"
        
        return f"""
📦 **{item_name}** @ {hub_name}
---
💰 最高买价: {buy_str} ISK
💸 最低卖价: {sell_str} ISK{spread_info}
""".strip()
    
    async def terminate(self):
        logger.info("EVE市场插件已卸载")
