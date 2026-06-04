import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("astrbot_plugin_eve_market", "你的名字", "EVE Online市场查询插件", "1.0.0", "仓库地址")
class EveMarketPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.base_url = "https://esi.evetech.net/latest"
    
    @filter.command("market")
    async def query_market(self, event: AstrMessageEvent):
        # 兼容性获取消息文本
        if hasattr(event, 'get_plain_text'):
            message_text = event.get_plain_text()
        elif hasattr(event, 'message_str'):
            message_text = event.message_str
        else:
            message_text = str(event.message)
        
        parts = message_text.strip().split()
        if len(parts) < 2:
            yield event.plain_result("请提供物品名称！\n用法：/market <物品名称> [区域ID]")
            return
        
        args = parts[1:]
        item_name = args[0]
        region_id = 10000002  # 默认吉他
        
        if len(args) > 1:
            try:
                region_id = int(args[1])
            except ValueError:
                yield event.plain_result(f"区域ID必须是数字：{args[1]}")
                return
        
        yield event.plain_result(f"正在查询 {item_name} 在区域 {region_id}...")
        
        try:
            type_id = await self._get_type_id(item_name)
            if not type_id:
                yield event.plain_result(f"未找到物品 '{item_name}'")
                return
            
            orders = await self._get_market_orders(region_id, type_id)
            if not orders:
                yield event.plain_result(f"未找到 {item_name} 的市场订单")
                return
            
            # 处理并返回结果
            result = self._format_market_data(item_name, region_id, orders)
            yield event.plain_result(result)
            
        except Exception as e:
            logger.error(f"查询失败: {e}")
            yield event.plain_result(f"查询失败: {str(e)}")
    
    async def _get_type_id(self, item_name: str) -> int:
        """支持中英文的物品ID搜索"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/universe/search/"
            params = {
                "categories": "inventory_type",
                "search": item_name,
                "language": "zh",
                "strict": "false"
            }
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        types = data.get('inventory_type', [])
                        if types:
                            logger.info(f"物品 '{item_name}' -> ID: {types[0]}")
                            return types[0]
                    return None
            except Exception as e:
                logger.error(f"搜索失败: {e}")
                return None
    
    async def _get_market_orders(self, region_id: int, type_id: int) -> list:
        """获取市场订单"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/markets/{region_id}/orders/"
            params = {"type_id": type_id, "order_type": "all"}
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return []
            except Exception as e:
                logger.error(f"获取订单失败: {e}")
                return []
    
    def _format_market_data(self, item_name: str, region_id: int, orders: list) -> str:
        """格式化市场数据输出"""
        buy_orders = [o for o in orders if o.get('is_buy_order', False)]
        sell_orders = [o for o in orders if not o.get('is_buy_order', False)]
        
        result = f"【{item_name}】市场行情 (区域ID: {region_id})\n"
        
        if sell_orders:
            top_sell = sorted(sell_orders, key=lambda x: x['price'])[:5]
            result += "\n📈 最低卖价:\n"
            for i, order in enumerate(top_sell, 1):
                result += f"  {i}. {order['price']:,.2f} ISK (库存: {order['volume_remain']:,})\n"
            result += f"\n⭐ 最优卖价: {top_sell[0]['price']:,.2f} ISK\n"
        
        if buy_orders:
            top_buy = sorted(buy_orders, key=lambda x: x['price'], reverse=True)[:5]
            result += "\n📉 最高买价:\n"
            for i, order in enumerate(top_buy, 1):
                result += f"  {i}. {order['price']:,.2f} ISK (库存: {order['volume_remain']:,})\n"
            result += f"\n⭐ 最优买价: {top_buy[0]['price']:,.2f} ISK\n"
        
        result += f"\n📊 订单统计: 卖单 {len(sell_orders)} / 买单 {len(buy_orders)}"
        
        if sell_orders and buy_orders:
            spread = top_sell[0]['price'] - top_buy[0]['price']
            result += f"\n💰 买卖差价: {spread:,.2f} ISK"
        
        return result
