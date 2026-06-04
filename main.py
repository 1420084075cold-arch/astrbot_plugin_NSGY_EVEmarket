import aiohttp
import os
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

from astrbot.api.all import (
    AstrMessageEvent,
    Command,
    Context,
    MessageEventResult,
    Plain,
    MessageChain,
)
from astrbot.api.plugin import Plugin, PluginMetadata

# ============================================
# 第一部分：插件元数据
# ============================================
metadata = PluginMetadata(
    name="EVE市场查询",           # 插件名称
    description="查询EVE Online市场物品价格信息，支持代理",  # 插件描述
    author="YourName",            # 作者
    version="1.0.0",              # 版本号
)


# ============================================
# 第二部分：数据类定义
# ============================================
@dataclass
class MarketOrder:
    """市场订单数据类"""
    item_name: str      # 物品名称
    order_type: str     # 订单类型：buy/sell
    price: float        # 价格
    volume: int         # 数量
    location: str       # 地点
    range: str          # 范围
    remaining: int      # 剩余数量


# ============================================
# 第三部分：EVE API接口类
# ============================================
class EVEMarketAPI:
    """EVE市场API接口类，负责与EVE Online服务器通信"""
    
    BASE_URL = "https://esi.evetech.net/latest"  # EVE API基础地址
    
    def __init__(self, proxy_url: str = None):
        """
        初始化API接口
        Args:
            proxy_url: 代理地址，如 "http://127.0.0.1:7890"
        """
        self.session = None
        self.proxy_url = proxy_url
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "AstrBot-EVE-Market-Plugin/1.0",
                    "Accept": "application/json"
                },
                timeout=timeout
            )
        return self.session
    
    async def search_item(self, item_name: str) -> Optional[Dict[str, Any]]:
        """
        搜索物品并返回物品信息
        Args:
            item_name: 物品名称
        Returns:
            物品信息字典，包含type_id和name等
        """
        session = await self._get_session()
        
        # 第一步：搜索物品ID
        search_url = f"{self.BASE_URL}/search/"
        search_params = {
            "categories": "inventory_type",
            "search": item_name,
            "strict": "false"
        }
        
        try:
            async with session.get(
                search_url, 
                params=search_params, 
                proxy=self.proxy_url
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if "inventory_type" in data and data["inventory_type"]:
                        # 第二步：获取第一个匹配物品的详细信息
                        type_id = data["inventory_type"][0]
                        return await self._get_item_info(type_id)
        except Exception as e:
            print(f"搜索物品失败: {e}")
        return None
    
    async def _get_item_info(self, type_id: int) -> Optional[Dict[str, Any]]:
        """获取物品详细信息"""
        session = await self._get_session()
        url = f"{self.BASE_URL}/universe/types/{type_id}/"
        
        try:
            async with session.get(url, proxy=self.proxy_url) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            print(f"获取物品信息失败: {e}")
        return None
    
    async def get_market_orders(
        self, 
        region_id: int, 
        type_id: int, 
        order_type: str = "all"
    ) -> List[MarketOrder]:
        """
        获取市场订单
        Args:
            region_id: 星域ID
            type_id: 物品类型ID
            order_type: 订单类型，"buy"、"sell"或"all"
        Returns:
            市场订单列表
        """
        session = await self._get_session()
        url = f"{self.BASE_URL}/markets/{region_id}/orders/"
        params = {"type_id": type_id}
        
        # 如果指定了订单类型，添加参数
        if order_type != "all":
            params["order_type"] = order_type
        
        try:
            async with session.get(
                url, 
                params=params, 
                proxy=self.proxy_url
            ) as response:
                if response.status == 200:
                    orders_data = await response.json()
                    return await self._process_orders(orders_data)
        except Exception as e:
            print(f"获取市场订单失败: {e}")
        return []
    
    async def _process_orders(self, orders_data: List[Dict]) -> List[MarketOrder]:
        """处理原始订单数据，转换为MarketOrder对象"""
        orders = []
        location_cache = {}  # 位置名称缓存
        
        for order in orders_data[:20]:  # 只处理前20个订单
            location_id = order.get("location_id")
            
            # 获取位置名称（使用缓存）
            if location_id not in location_cache:
                location_name = await self._get_location_name(location_id)
                location_cache[location_id] = location_name
            else:
                location_name = location_cache[location_id]
            
            # 判断订单类型
            is_buy_order = order.get("is_buy_order", False)
            order_type = "buy" if is_buy_order else "sell"
            
            market_order = MarketOrder(
                item_name="",  # 稍后填充
                order_type=order_type,
                price=order.get("price", 0),
                volume=order.get("volume_total", 0),
                location=location_name,
                range=order.get("range", "station"),
                remaining=order.get("volume_remain", 0)
            )
            orders.append(market_order)
        
        return orders
    
    async def _get_location_name(self, location_id: int) -> str:
        """获取位置名称（空间站名称）"""
        session = await self._get_session()
        
        # 先尝试查询空间站
        url = f"{self.BASE_URL}/universe/stations/{location_id}/"
        try:
            async with session.get(url, proxy=self.proxy_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("name", f"Station-{location_id}")
        except:
            pass
        
        # 如果不是空间站，返回ID
        return f"Location-{location_id}"
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session and not self.session.closed:
            await self.session.close()


# ============================================
# 第四部分：主插件类
# ============================================
class EVEMarketPlugin(Plugin):
    """EVE市场查询主插件类"""
    
    # 常用星域ID映射表
    REGIONS = {
        "吉他": 10000002,    # The Forge
        "艾玛": 10000043,    # Domain
        "加达里": 10000014,  # Lonetrek
        "米玛塔尔": 10000030,  # Heimatar
        "盖伦特": 10000037,  # Essence
    }
    
    def __init__(self, context: Context):
        """
        插件初始化
        Args:
            context: AstrBot上下文
        """
        super().__init__(context)
        
        # 加载配置
        config = self._load_config()
        
        # 设置代理
        proxy_url = None
        if config.get("proxy", {}).get("enabled", False):
            proxy_url = config["proxy"]["url"]
            print(f"[EVE插件] 使用代理: {proxy_url}")
        
        # 初始化API接口
        self.market_api = EVEMarketAPI(proxy_url=proxy_url)
    
    def _load_config(self) -> Dict:
        """加载配置文件"""
        config_path = os.path.join(
            os.path.dirname(__file__), 
            'eve_market_config.json'
        )
        
        default_config = {
            "proxy": {
                "enabled": False,
                "url": "http://127.0.0.1:7890",
                "type": "http"
            }
        }
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # 创建默认配置文件
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            return default_config
    
    # ============================================
    # 第五部分：命令处理函数
    # ============================================
    
    @Command("eve", "eve查询")
    async def query_market(self, event: AstrMessageEvent):
        """
        查询EVE市场价格
        用法: /eve [物品名称] [星域名称]
        示例: /eve 三钛合金 吉他
        """
        message_str = str(event.message).strip()
        parts = message_str.split()
        
        # 参数检查
        if len(parts) < 2:
            yield self._format_result("❌ 使用方法: /eve [物品名称] [星域名称]\n"
                                    "示例: /eve 三钛合金 吉他\n"
                                    "可用星域: " + ", ".join(self.REGIONS.keys()))
            return
        
        item_name = parts[1]
        region_name = parts[2] if len(parts) > 2 else "吉他"
        
        # 验证星域
        region_id = self.REGIONS.get(region_name)
        if not region_id:
            yield self._format_result(f"❌ 未知星域: {region_name}\n"
                                    f"可用星域: {', '.join(self.REGIONS.keys())}")
            return
        
        # 搜索物品
        item_info = await self.market_api.search_item(item_name)
        if not item_info:
            yield self._format_result(f"❌ 未找到物品: {item_name}")
            return
        
        type_id = item_info["type_id"]
        item_name_found = item_info.get("name", item_name)
        
        # 获取买卖订单
        sell_orders = await self.market_api.get_market_orders(region_id, type_id, "sell")
        buy_orders = await self.market_api.get_market_orders(region_id, type_id, "buy")
        
        # 排序：卖单从低到高，买单从高到低
        sell_orders.sort(key=lambda x: x.price)
        buy_orders.sort(key=lambda x: x.price, reverse=True)
        
        # 构建返回结果
        result = self._build_market_report(
            item_name_found, region_name, sell_orders, buy_orders
        )
        
        yield self._format_result(result)
    
    @Command("eve_price", "eve价格")
    async def quick_price(self, event: AstrMessageEvent):
        """
        快速查询价格（默认吉他星系）
        用法: /eve_price [物品名称]
        """
        message_str = str(event.message).strip()
        parts = message_str.split()
        
        if len(parts) < 2:
            yield self._format_result("❌ 使用方法: /eve_price [物品名称]\n"
                                    "示例: /eve_price 三钛合金")
            return
        
        item_name = " ".join(parts[1:])
        region_id = self.REGIONS["吉他"]  # 默认吉他
        
        # 搜索物品
        item_info = await self.market_api.search_item(item_name)
        if not item_info:
            yield self._format_result(f"❌ 未找到物品: {item_name}")
            return
        
        type_id = item_info["type_id"]
        item_name_found = item_info.get("name", item_name)
        
        # 获取订单
        sell_orders = await self.market_api.get_market_orders(region_id, type_id, "sell")
        buy_orders = await self.market_api.get_market_orders(region_id, type_id, "buy")
        
        # 构建快速价格报告
        result = self._build_quick_price_report(item_name_found, sell_orders, buy_orders)
        yield self._format_result(result)
    
    @Command("eve_search", "搜索物品")
    async def search_items(self, event: AstrMessageEvent):
        """
        搜索EVE物品
        用法: /eve_search [关键词]
        """
        message_str = str(event.message).strip()
        parts = message_str.split()
        
        if len(parts) < 2:
            yield self._format_result("❌ 使用方法: /eve_search [关键词]\n"
                                    "示例: /eve_search 凤凰级")
            return
        
        keyword = " ".join(parts[1:])
        
        # 直接搜索
        session = await self.market_api._get_session()
        url = f"{self.market_api.BASE_URL}/search/"
        params = {
            "categories": "inventory_type",
            "search": keyword,
            "strict": "false"
        }
        
        try:
            async with session.get(
                url, 
                params=params, 
                proxy=self.market_api.proxy_url
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if "inventory_type" in data and data["inventory_type"]:
                        type_ids = data["inventory_type"][:10]
                        
                        # 获取物品名称
                        items_info = []
                        for type_id in type_ids:
                            info = await self.market_api._get_item_info(type_id)
                            if info:
                                items_info.append(info)
                        
                        if items_info:
                            result = f"🔍 搜索 '{keyword}' 的结果:\n"
                            result += "=" * 30 + "\n"
                            for i, item in enumerate(items_info, 1):
                                result += f"{i}. {item['name']} (ID: {item['type_id']})\n"
                            
                            yield self._format_result(result)
                            return
                    
                    yield self._format_result(f"❌ 未找到与 '{keyword}' 相关的物品")
        except Exception as e:
            yield self._format_result(f"❌ 搜索出错: {str(e)}")
    
    @Command("eve_help", "eve帮助")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """
🚀 EVE Online 市场查询插件

📋 可用命令:
• /eve [物品名] [星域] - 查询市场价格
• /eve_price [物品名] - 快速查价(吉他)
• /eve_search [关键词] - 搜索物品
• /eve_help - 显示帮助

🌍 可用星域:
吉他、艾玛、加达里、米玛塔尔、盖伦特

📝 示例:
/eve 三钛合金 吉他
/eve_price 同位素-5
        """
        yield self._format_result(help_text.strip())
    
    # ============================================
    # 第六部分：辅助函数（构建返回结果）
    # ============================================
    
    def _build_market_report(
        self, 
        item_name: str, 
        region_name: str,
        sell_orders: List[MarketOrder], 
        buy_orders: List[MarketOrder]
    ) -> str:
        """构建详细市场报告"""
        result = f"📊 {item_name} - {region_name}市场行情\n"
        result += "=" * 30 + "\n"
        
        if not sell_orders and not buy_orders:
            result += "暂无市场数据\n"
            return result
        
        # 最低卖价
        if sell_orders:
            min_sell = sell_orders[0]
            result += f"📈 最低卖价: {min_sell.price:,.2f} ISK\n"
            result += f"   数量: {min_sell.remaining:,}\n"
            result += f"   地点: {min_sell.location}\n\n"
        
        # 最高买价
        if buy_orders:
            max_buy = buy_orders[0]
            result += f"📉 最高买价: {max_buy.price:,.2f} ISK\n"
            result += f"   数量: {max_buy.remaining:,}\n"
            result += f"   地点: {max_buy.location}\n\n"
        
        # 价差分析
        if sell_orders and buy_orders:
            spread = max_buy.price - min_sell.price
            spread_percent = (spread / min_sell.price) * 100 if min_sell.price > 0 else 0
            result += f"💰 买卖价差: {spread:,.2f} ISK ({spread_percent:+.1f}%)\n"
        
        # 前5个卖单
        if len(sell_orders) > 1:
            result += "\n📋 最低5个卖单:\n"
            for i, order in enumerate(sell_orders[:5], 1):
                result += f"  {i}. {order.price:,.2f} ISK x{order.remaining:,}\n"
        
        # 前5个买单
        if len(buy_orders) > 1:
            result += "\n📋 最高5个买单:\n"
            for i, order in enumerate(buy_orders[:5], 1):
                result += f"  {i}. {order.price:,.2f} ISK x{order.remaining:,}\n"
        
        result += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return result
    
    def _build_quick_price_report(
        self,
        item_name: str,
        sell_orders: List[MarketOrder],
        buy_orders: List[MarketOrder]
    ) -> str:
        """构建快速价格报告"""
        if not sell_orders and not buy_orders:
            return f"❌ {item_name} 在吉他星系暂无市场订单"
        
        sell_orders.sort(key=lambda x: x.price)
        buy_orders.sort(key=lambda x: x.price, reverse=True)
        
        result = f"💹 {item_name} - 吉他市场\n"
        
        if sell_orders:
            result += f"最低卖价: {sell_orders[0].price:,.2f} ISK\n"
        
        if buy_orders:
            result += f"最高买价: {buy_orders[0].price:,.2f} ISK\n"
        
        if sell_orders and buy_orders:
            avg_price = (sell_orders[0].price + buy_orders[0].price) / 2
            result += f"参考价格: {avg_price:,.2f} ISK\n"
        
        return result
    
    def _format_result(self, text: str) -> MessageEventResult:
        """格式化返回结果"""
        return MessageEventResult(MessageChain([Plain(text)]))
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """插件退出时清理资源"""
        await self.market_api.close()


# ============================================
# 第七部分：插件入口
# ============================================
def create_plugin(context: Context) -> Plugin:
    """
    插件创建函数（AstrBot调用此函数创建插件实例）
    Args:
        context: AstrBot上下文
    Returns:
        插件实例
    """
    return EVEMarketPlugin(context)
