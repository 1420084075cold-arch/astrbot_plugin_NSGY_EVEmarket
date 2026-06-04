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
        # 修复1：使用正确的方法获取消息文本
        # 对于 AiocqhttpMessageEvent，应该使用 event.message_str 或 str(event.message)
        try:
            # 尝试多种获取消息文本的方式
            if hasattr(event, 'get_plain_text'):
                message_text = event.get_plain_text()
            elif hasattr(event, 'message_str'):
                message_text = event.message_str
            else:
                message_text = str(event.message)
        except Exception as e:
            logger.error(f"获取消息文本失败: {e}")
            yield event.plain_result("获取消息内容失败")
            return
        
        # 解析命令和参数
        parts = message_text.strip().split()
        if len(parts) < 2:
            yield event.plain_result("请提供物品名称！\n用法：/market 核心扫描器 10000002\n区域ID可选，默认为吉他(10000002)")
            return
        
        # 获取参数：/market 后面的部分
        args = parts[1:]
        item_name = args[0]
        
        # 处理区域ID（可选参数）
        region_id = 10000002  # 默认吉他
        if len(args) > 1:
            try:
                region_id = int(args[1])
            except ValueError:
                yield event.plain_result(f"区域ID必须是数字，你输入的是：{args[1]}")
                return
        
        # 发送提示消息
        yield event.plain_result(f"正在查询 {item_name} 在区域 {region_id} 的市场订单...")
        
        try:
            # 第一步：获取物品Type ID
            type_id = await self._get_type_id(item_name)
            if not type_id:
                yield event.plain_result(f"未找到物品 '{item_name}'，请检查物品名称是否正确（建议使用EVE官方中文名）")
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
                # 获取最低的5个卖单
                top_sell = sorted(sell_orders, key=lambda x: x['price'])[:5]
                result += "\n📈 最低卖价:\n"
                for i, order in enumerate(top_sell, 1):
                    result += f"  {i}. {order['price']:,.2f} ISK (数量: {order['volume_remain']:,})\n"
                
                lowest_sell = top_sell[0]
                result += f"\n⭐ 最优卖价: {lowest_sell['price']:,.2f} ISK\n"
            
            if buy_orders:
                # 获取最高的5个买单
                top_buy = sorted(buy_orders, key=lambda x: x['price'], reverse=True)[:5]
                result += "\n📉 最高买价:\n"
                for i, order in enumerate(top_buy, 1):
                    result += f"  {i}. {order['price']:,.2f} ISK (数量: {order['volume_remain']:,})\n"
                
                highest_buy = top_buy[0]
                result += f"\n⭐ 最优买价: {highest_buy['price']:,.2f} ISK\n"
            
            result += f"\n📊 总订单数: {len(orders)} (卖单:{len(sell_orders)}/买单:{len(buy_orders)})"
            
            # 添加价格差额信息
            if sell_orders and buy_orders:
                spread = lowest_sell['price'] - highest_buy['price']
                result += f"\n💰 买卖差价: {spread:,.2f} ISK"
            
            yield event.plain_result(result)
            
        except aiohttp.ClientError as e:
            logger.error(f"网络请求失败: {e}")
            yield event.plain_result(f"网络请求失败，请稍后重试\n错误: {str(e)}")
        except Exception as e:
            logger.error(f"查询失败: {e}")
            yield event.plain_result(f"查询失败: {str(e)}\n请检查物品名称是否正确")
    
  async def _get_type_id(self, item_name: str) -> int:
    """搜索物品ID，现在支持中英文了！"""
    async with aiohttp.ClientSession() as session:
        # 这里的核心技巧是设置 language="zh"，让EVE官方服务器帮我们做翻译和匹配
        url = f"{self.base_url}/universe/search/"
        params = {
            "categories": "inventory_type",
            "search": item_name,
            "language": "zh",  # 请求中文结果，这样“PLEX”也能匹配到正确的物品
            "strict": "false"  # 模糊搜索，提高容错率
        }
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    types = data.get('inventory_type', [])
                    if types:
                        # 找到了就返回第一个（通常是最佳匹配）
                        found_id = types[0]
                        logger.info(f"物品 '{item_name}' 匹配到ID: {found_id}")
                        return found_id
                    else:
                        # 如果没找到，给你个更友好的提示
                        logger.warning(f"未找到物品 '{item_name}'")
                        return None
                else:
                    logger.error(f"ESI搜索失败: HTTP {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"搜索物品ID时出错: {e}")
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
                    elif resp.status == 404:
                        return []
                    else:
                        logger.error(f"ESI市场订单失败: HTTP {resp.status}")
                        return []
            except Exception as e:
                logger.error(f"获取市场订单异常: {e}")
                return []
