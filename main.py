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

# fuzzwork API 端点
FUZZWORK_TYPE_ID = "https://www.fuzzwork.co.uk/api/typeid.php?typename={name}"
# Eve-Marketer API (无需API Key)
MARKET_API = "https://eve-marketer.com/api/v1/market/{type_id}/{region_id}"


@register("eve_market", "YourName", "EVE Online 欧服市场查询插件", "1.0.0")
class EveMarketPlugin(AstrBotPlugin):
    async def initialize(self):
        """插件初始化"""
        logger.info("EVE市场插件已加载")
    
    @filter.command("market")
    async def query_market(self, event: MessageEventResult):
        """用法: /market <物品名> [贸易中心]
        示例: /market Plex jita
             /market 导弹
             /market 星币
        """
        # 解析用户输入
        input_text = event.message_str.strip()
        parts = input_text.split()
        
        if len(parts) < 2:
            yield event.plain_result("用法: /market <物品名> [贸易中心]\n默认贸易中心: Jita\n示例: /market Plex jita")
            return
        
        # 提取物品名（可能包含空格，如 "Antimatter S"）
        if len(parts) > 2 and parts[2].lower() in TRADE_HUBS:
            # 格式: /market 物品名 贸易中心
            item_name = parts[1]
            hub_key = parts[2].lower()
        elif len(parts) > 2:
            # 物品名包含空格的情况: /market Antimatter S jita
            # 找出贸易中心的位置
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
        else:
            item_name = parts[1]
            hub_key = "jita"
        
        if hub_key not in TRADE_HUBS:
            hub_names = ", ".join(TRADE_HUBS.keys())
            yield event.plain_result(f"不支持的贸易中心: {hub_key}\n支持: {hub_names}\n示例: /market Plex jita")
            return
        
        hub = TRADE_HUBS[hub_key]
        
        # 发送"处理中"提示
        yield event.plain_result(f"正在查询 {item_name} 在 {hub['name']} 的价格...")
        
        # 1. 使用 fuzzwork 搜索物品ID
        type_id, matched_name = await self._search_item_fuzzwork(item_name)
        if not type_id:
            yield event.plain_result(f"未找到物品: {item_name}\n提示：请尝试使用英文名称，如 'Plex'、'Antimatter S'")
            return
        
        # 2. 查询市场数据
        market_data = await self._fetch_market_data(type_id, hub['id'])
        if not market_data:
            yield event.plain_result(f"无法获取 {matched_name} 的市场数据")
            return
        
        # 3. 格式化输出
        result = self._format_price(matched_name, hub['name'], market_data)
        yield event.plain_result(result)
    
    async def _search_item_fuzzwork(self, name: str) -> tuple[Optional[int], Optional[str]]:
        """使用 fuzzwork API 搜索物品，返回 (type_id, 标准名称)"""
        try:
            # fuzzwork API 会自动匹配最接近的物品名称
            url = FUZZWORK_TYPE_ID.format(name=name)
            headers = {
                "User-Agent": "AstrBot-EVE-Market-Plugin/1.0",
                "Accept": "application/json"
            }
            
            async with self.http_client.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"fuzzwork 返回数据: {data}")
                    
                    # fuzzwork 返回格式: {"typeID": 12345, "typeName": "物品名称"}
                    if isinstance(data, dict) and "typeID" in data:
                        type_id = data["typeID"]
                        matched_name = data.get("typeName", name)
                        logger.info(f"找到物品: {name} -> {matched_name} (ID: {type_id})")
                        return type_id, matched_name
                    
                    # 有些版本返回列表
                    if isinstance(data, list) and len(data) > 0:
                        first_match = data[0]
                        if "typeID" in first_match:
                            return first_match["typeID"], first_match.get("typeName", name)
                
                logger.warning(f"fuzzwork 未找到物品: {name}, 状态码: {resp.status}")
                return None, None
                
        except Exception as e:
            logger.error(f"fuzzwork 搜索失败: {e}")
            return None, None
    
    async def _fetch_market_data(self, type_id: int, region_id: int) -> Optional[Dict[str, Any]]:
        """获取市场订单数据"""
        try:
            url = MARKET_API.format(type_id=type_id, region_id=region_id)
            headers = {"User-Agent": "AstrBot-EVE-Market-Plugin/1.0"}
            
            async with self.http_client.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Eve-Marketer 返回结构: {"buy": {"max": ..., "min": ...}, "sell": {"min": ..., "max": ...}}
                    return {
                        "buy_max": data.get("buy", {}).get("max", 0),
                        "sell_min": data.get("sell", {}).get("min", 0),
                    }
                else:
                    logger.warning(f"获取市场数据失败: HTTP {resp.status}")
                return None
        except Exception as e:
            logger.error(f"获取市场数据失败: {e}")
            return None
    
    def _format_price(self, item_name: str, hub_name: str, data: Dict) -> str:
        """格式化输出价格信息"""
        buy_max = data.get("buy_max", 0)
        sell_min = data.get("sell_min", 0)
        
        # 格式化数字 (添加千位分隔符)
        buy_str = f"{buy_max:,.2f}" if buy_max > 0 else "暂无买盘"
        sell_str = f"{sell_min:,.2f}" if sell_min > 0 else "暂无卖盘"
        
        # 计算差价和利润率
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
    
    @filter.command("markets")
    async def list_hubs(self, event: MessageEventResult):
        """列出所有支持的贸易中心"""
        hubs = "\n".join([f"• {v['name']} ({k})" for k, v in TRADE_HUBS.items()])
        yield event.plain_result(f"支持的贸易中心:\n{hubs}\n\n使用示例:\n/market Plex jita\n/market Antimatter S")
    
    @filter.command("search")
    async def search_item(self, event: MessageEventResult):
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
