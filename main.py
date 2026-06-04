import json
from typing import Optional, Dict, Any, Tuple

# 修正导入部分
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
from astrbot.core.config.client import AstrBotConfig

# API 端点保持不变
TRADE_HUBS = {
    "jita": {"id": 30000142, "name": "Jita"},
    "amarr": {"id": 30002187, "name": "Amarr"},
    "dodixie": {"id": 30002659, "name": "Dodixie"},
    "rens": {"id": 30002510, "name": "Rens"},
    "hek": {"id": 30002053, "name": "Hek"},
}
FUZZWORK_TYPE_ID = "https://www.fuzzwork.co.uk/api/typeid.php?typename={name}"
MARKET_API = "https://eve-marketer.com/api/v1/market/{type_id}/{region_id}"

# 主要改动：不再使用 @register，而是通过 metadata.yaml 声明插件，并继承 Star 类
class EveMarketPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 可以在这里初始化插件需要的 HTTP 客户端或其他资源
    
    # 使用 filter.command 装饰器注册指令
    @filter.command("market")
    async def query_market(self, event: AstrMessageEvent):
        """用法: /market <物品名> [贸易中心]"""
        input_text = event.message_str.strip()
        parts = input_text.split()
        
        if len(parts) < 2:
            yield event.plain_result("用法: /market <物品名> [贸易中心]\n默认贸易中心: Jita\n示例: /market Plex jita")
            return
        
        # 解析逻辑保持不变...
        if len(parts) > 2 and parts[2].lower() in TRADE_HUBS:
            item_name = parts[1]
            hub_key = parts[2].lower()
        else:
            # 处理物品名含空格的情况
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
            yield event.plain_result(f"不支持的贸易中心: {hub_key}\n支持: {hub_names}\n示例: /market Plex jita")
            return
        
        hub = TRADE_HUBS[hub_key]
        
        # 发送提示
        yield event.plain_result(f"正在查询 {item_name} 在 {hub['name']} 的价格...")
        
        # 使用 fuzzwork 搜索
        type_id, matched_name = await self._search_item_fuzzwork(item_name)
        if not type_id:
            yield event.plain_result(f"未找到物品: {item_name}\n提示：请尝试使用英文名称，如 'Plex'、'Antimatter S'")
            return
        
        # 获取市场数据
        market_data = await self._fetch_market_data(type_id, hub['id'])
        if not market_data:
            yield event.plain_result(f"无法获取 {matched_name} 的市场数据")
            return
        
        # 格式化输出
        result = self._format_price(matched_name, hub['name'], market_data)
        yield event.plain_result(result)
    
    @filter.command("markets")
    async def list_hubs(self, event: AstrMessageEvent):
        """列出所有支持的贸易中心"""
        hubs = "\n".join([f"• {v['name']} ({k})" for k, v in TRADE_HUBS.items()])
        yield event.plain_result(f"支持的贸易中心:\n{hubs}\n\n使用示例:\n/market Plex jita\n/market Antimatter S")
    
    @filter.command("search")
    async def search_item(self, event: AstrMessageEvent):
        """搜索物品ID: /search <物品名>"""
        parts = event.message_str.strip().split()
        if len(parts) < 2:
            yield event.plain_result("用法: /search <物品名>\n示例: /search Plex")
            return
        
        item_name = ' '.join(parts[1:])
        yield event.plain_result(f"正在搜索: {item_name}...")
        
        type_id, matched_name = await self._search_item_fuzzwork(item_name)
        if type_id:
            yield event.plain_result(f"✅ 找到物品: {matched_name}\nType ID: {type_id}")
        else:
            yield event.plain_result(f"❌ 未找到物品: {item_name}")
    
    # 以下三个辅助方法保持不变，但注意 _fetch_market_data 中的 self.http_client
    async def _search_item_fuzzwork(self, name: str) -> Tuple[Optional[int], Optional[str]]:
        """使用 fuzzwork API 搜索物品"""
        try:
            url = FUZZWORK_TYPE_ID.format(name=name)
            headers = {
                "User-Agent": "AstrBot-EVE-Market-Plugin/1.0",
                "Accept": "application/json"
            }
            # 注意：在新版 AstrBot 中，可以通过 self.context.http_client 获取客户端
            # 或者直接使用 aiohttp 创建客户端
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"fuzzwork 返回数据: {data}")
                        if isinstance(data, dict) and "typeID" in data:
                            return data["typeID"], data.get("typeName", name)
            return None, None
        except Exception as e:
            logger.error(f"fuzzwork 搜索失败: {e}")
            return None, None
    
    async def _fetch_market_data(self, type_id: int, region_id: int) -> Optional[Dict[str, Any]]:
        """获取市场订单数据"""
        try:
            url = MARKET_API.format(type_id=type_id, region_id=region_id)
            headers = {"User-Agent": "AstrBot-EVE-Market-Plugin/1.0"}
            import aiohttp
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
    
    def _format_price(self, item_name: str, hub_name: str, data: Dict) -> str:
        """格式化输出价格信息"""
        buy_max = data.get("buy_max", 0)
        sell_min = data.get("sell_min", 0)
        
        buy_str = f"{buy_max:,.2f}" if buy_max > 0 else "暂无买盘"
        sell_str = f"{sell_min:,.2f}" if sell_min > 0 else "暂无卖盘"
        
        spread_info = ""
        if buy_max > 0 and sell_min > 0 and sell_min > buy_max:
            spread = sell_min - buy_max
            profit_pct = (spread / buy_max) * 100
            spread_info = f"\n📊 **差价**: {spread:,.2f} ISK ({profit_pct:.1f}%)"
        
        result = f"""
📦 **{item_name}** 市场行情 @ {hub_name}
---
💰 **最高买价**: {buy_str} ISK
💸 **最低卖价**: {sell_str} ISK{spread_info}
"""
        return result.strip()
    
    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("EVE市场插件已卸载")
