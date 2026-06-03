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
        """查询EVE市场价格，用法：/market <物品名称> [region_id]"""
        # 获取指令参数
        args = event.get_plain_text().split()[1:]  # 分割命令和参数
        if not args:
            yield event.plain_result("请提供物品名称！\n用法：/market 核心扫描器 10000002")
            return
        
        # 解析参数：物品名称和可选的区域ID
        item_name = args[0]
        region_id = int(args[1]) if len(args) > 1 else 10000002  # 默认吉他
        
        # 发送提示消息
        yield event.plain_result(f"正在查询 {item_name} 在区域 {region_id} 的市场订单...")
        
        try:
            # 第一步：获取物品Type ID
            type_id = await self._get_type_id(item_name)
            if not type_id:
                yield event.plain_result(f"未找到物品 '{item_name}'，请检查名称")
                return
            
            # 第二步：查询市场订单
            orders = await self._get_market_orders(region_id, type_id)
            
            # 第三步：处理并返回结果
            if not orders:
                yield event.plain_result(f"未找到 {item_name} 的市场订单")
                return
            
            # 分离买家和卖家订单
            buy_orders = [o for o in orders if o.get('is_buy_order', False)]
            sell_orders = [o for o in orders if not o.get('is_buy_order', False)]
            
            # 格式化输出
            result = f"【{item_name}】市场行情 (区域ID: {region_id})\n"
            if sell_orders:
                lowest_sell = min(sell_orders, key=lambda x: x['price'])
                result += f"📈 最低卖价: {lowest_sell['price']:.2f} ISK (地点: {lowest_sell.get('location_id', '未知')})\n"
            if buy_orders:
                highest_buy = max(buy_orders, key=lambda x: x['price'])
                result += f"📉 最高买价: {highest_buy['price']:.2f} ISK (地点: {highest_buy.get('location_id', '未知')})\n"
            result += f"\n总订单数: {len(orders)} (卖单:{len(sell_orders)}/买单:{len(buy_orders)})"
            
            yield event.plain_result(result)
            
        except Exception as e:
            logger.error(f"查询失败: {e}")
            yield event.plain_result(f"查询失败: {str(e)}")
    
    async def _get_type_id(self, item_name: str) -> int:
        """搜索物品ID"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/universe/search/"
            params = {"categories": "inventory_type", "search": item_name, "strict": "true"}
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('inventory_type', [None])[0]
        return None
    
    async def _get_market_orders(self, region_id: int, type_id: int) -> list:
        """获取市场订单"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/markets/{region_id}/orders/"
            params = {"type_id": type_id, "order_type": "all"}
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
        return []
