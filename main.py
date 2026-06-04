import json
from typing import Optional, Dict, Any
from astrbot.api.event import AstrBotPlugin, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Plain
from astrbot.api.logger import logger
from astrbot.api.filter import filter

# 贸易中心星系ID (欧服常见)
TRADE_HUBS = {
    "jita": {"id": 30000142, "name": "Jita"},
    "amarr": {"id": 30002187, "name": "Amarr"},
    "dodixie": {"id": 30002659, "name": "Dodixie"},
    "rens": {"id": 30002510, "name": "Rens"},
    "hek": {"id": 30002053, "name": "Hek"},
}

# Eve-Marketer API (免费，无需API Key)
MARKET_API = "https://eve-marketer.com/api/v1/market/{type_id}/{region_id}"

# ESI 端点用于搜索物品ID
ESI_SEARCH = "https://esi.evetech.net/latest/search/?categories=inventory_type&datasource=tranquility&language=en&search={name}"


@register("eve_market", "YourName", "EVE Online 欧服市场查询插件", "1.0.0")
class EveMarketPlugin(AstrBotPlugin):
    async def initialize(self):
        """插件初始化"""
        logger.info("EVE市场插件已加载")
    
    @filter.command("market")
    async def query_market(self, event: MessageEventResult):
        """用法: /market <物品名> [贸易中心]
        示例: /market plex jita
             /market 导弹
        """
        # 解析用户输入
        input_text = event.message_str.strip()
        parts = input_text.split()
        
        if len(parts) < 2:
            yield event.plain_result("用法: /market <物品名> [贸易中心]\n默认贸易中心: Jita\n示例: /market plex jita")
            return
        
        # 提取物品名和贸易中心
        item_name = parts[1]
        hub_key = parts[2].lower() if len(parts) > 2 else "jita"
        
        if hub_key not in TRADE_HUBS:
            hub_names = ", ".join(TRADE_HUBS.keys())
            yield event.plain_result(f"不支持的贸易中心: {hub_key}\n支持: {hub_names}")
            return
        
        hub = TRADE_HUBS[hub_key]
        
        # 发送"处理中"提示
        yield event.plain_result(f"正在查询 {item_name} 在 {hub['name']} 的价格...")
        
        # 1. 搜索物品ID
        type_id = await self._search_item(item_name)
        if not type_id:
            yield event.plain_result(f"未找到物品: {item_name}")
            return
        
        # 2. 查询市场数据
        market_data = await self._fetch_market_data(type_id, hub['id'])
        if not market_data:
            yield event.plain_result(f"无法获取 {item_name} 的市场数据")
            return
        
        # 3. 格式化输出
        result = self._format_price(item_name, hub['name'], market_data)
        yield event.plain_result(result)
    
    async def _search_item(self, name: str) -> Optional[int]:
        """搜索物品，返回type_id"""
        try:
            url = ESI_SEARCH.format(name=name)
            async with self.http_client.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # 获取第一个匹配的物品
                    if "inventory_type" in data and data["inventory_type"]:
                        return data["inventory_type"][0]
                return None
        except Exception as e:
            logger.error(f"搜索物品失败: {e}")
            return None
    
    async def _fetch_market_data(self, type_id: int, region_id: int) -> Optional[Dict[str, Any]]:
        """获取市场订单数据"""
        try:
            url = MARKET_API.format(type_id=type_id, region_id=region_id)
            async with self.http_client.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Eve-Marketer 返回结构: {"buy": {"max": ..., "min": ...}, "sell": {"min": ..., "max": ...}}
                    return {
                        "buy_max": data.get("buy", {}).get("max", 0),
                        "sell_min": data.get("sell", {}).get("min", 0),
                    }
                return None
        except Exception as e:
            logger.error(f"获取市场数据失败: {e}")
            return None
    
    def _format_price(self, item_name: str, hub_name: str, data: Dict) -> str:
        """格式化输出价格信息"""
        buy_max = data.get("buy_max", 0)
        sell_min = data.get("sell_min", 0)
        
        # 格式化数字 (添加千位分隔符)
        buy_str = f"{buy_max:,.2f}" if buy_max > 0 else "无订单"
        sell_str = f"{sell_min:,.2f}" if sell_min > 0 else "无订单"
        
        result = f"""
📦 **{item_name}** 市场行情 @ {hub_name}
---
💰 **最高买价**: {buy_str} ISK
💸 **最低卖价**: {sell_str} ISK
"""
        return result.strip()
    
    @filter.command("markets")
    async def list_hubs(self, event: MessageEventResult):
        """列出所有支持的贸易中心"""
        hubs = "\n".join([f"• {v['name']} ({k})" for k, v in TRADE_HUBS.items()])
        yield event.plain_result(f"支持的贸易中心:\n{hubs}")
