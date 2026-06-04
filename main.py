"""
EVE Online Market Plugin for Astribot
Author: Assistant
Description: A comprehensive market plugin for EVE Online
"""

import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import asyncio
import aiohttp
from dataclasses import dataclass
from enum import Enum

# ==================== Data Models ====================

class OrderType(Enum):
    BUY = "buy"
    SELL = "sell"

class Region(Enum):
    JITA = 10000002
    AMARR = 10000043
    DODIXIE = 10000032
    RENS = 10000030
    HEK = 10000042

@dataclass
class MarketOrder:
    """市场订单数据模型"""
    order_id: int
    type_id: int
    location_id: int
    volume_total: int
    volume_remain: int
    price: float
    is_buy_order: bool
    issued: datetime
    duration: int
    range: str
    
@dataclass
class MarketStats:
    """市场统计数据模型"""
    type_id: int
    type_name: str
    buy_price_max: float
    sell_price_min: float
    spread: float
    volume: int
    orders_count: int
    updated_at: datetime

# ==================== Market Plugin ====================

class EVEMarketPlugin:
    """EVE Online 市场插件主类"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.api_base = "https://esi.evetech.net/latest"
        self.cache = {}
        self.cache_duration = timedelta(minutes=5)
        self.session = None
        
        # 常用物品ID映射
        self.common_items = {
            "tritanium": 34,
            "pyrite": 35,
            "mexallon": 36,
            "isogen": 37,
            "nocxium": 38,
            "zydrine": 39,
            "megacyte": 40,
            "morphite": 11399,
            "plex": 44992,
            "injector": 40520,
            "veldspar": 1230,
            "scordite": 1228,
            "pyroxeres": 1224,
            "plagioclase": 18,
            "omber": 1227,
            "kernite": 20,
            "jaspet": 1226,
            "hemorphite": 1231,
            "hedbergite": 21,
            "gneiss": 1229,
            "dark_ochre": 1232,
            "crokite": 1225,
            "spodumain": 19,
            "bistot": 1223,
            "arkonor": 22,
            "mercoxit": 11396,
        }
        
        # 常用蓝图ID映射
        self.common_blueprints = {
            "avatar": 33193,
            "erebus": 33195,
            "leviathan": 33197,
            "ragnarok": 33199,
            "revelation": 33200,
            "moros": 33190,
            "naglfar": 33192,
            "phoenix": 33194,
        }

    # ==================== Core Methods ====================

    async def get_session(self):
        """获取或创建HTTP会话"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_market_orders(
        self, 
        region_id: int, 
        type_id: int, 
        order_type: OrderType = OrderType.SELL
    ) -> List[MarketOrder]:
        """获取指定区域和物品的市场订单"""
        cache_key = f"orders_{region_id}_{type_id}_{order_type.value}"
        
        # 检查缓存
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if datetime.now() - cached_time < self.cache_duration:
                return cached_data

        # 构建API URL
        url = f"{self.api_base}/markets/{region_id}/orders/"
        params = {
            "datasource": "tranquility",
            "order_type": order_type.value,
            "page": 1,
            "type_id": type_id,
        }

        try:
            session = await self.get_session()
            orders = []
            
            while True:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        for order_data in data:
                            order = MarketOrder(
                                order_id=order_data["order_id"],
                                type_id=order_data["type_id"],
                                location_id=order_data["location_id"],
                                volume_total=order_data["volume_total"],
                                volume_remain=order_data["volume_remain"],
                                price=order_data["price"],
                                is_buy_order=order_data["is_buy_order"],
                                issued=datetime.fromisoformat(
                                    order_data["issued"].replace("Z", "+00:00")
                                ),
                                duration=order_data["duration"],
                                range=order_data["range"],
                            )
                            orders.append(order)
                        
                        # 检查是否有下一页
                        if "x-pages" in response.headers:
                            total_pages = int(response.headers["x-pages"])
                            if params["page"] < total_pages:
                                params["page"] += 1
                                continue
                        break
                    else:
                        break

            # 缓存结果
            self.cache[cache_key] = (orders, datetime.now())
            return orders

        except Exception as e:
            print(f"Error fetching market orders: {e}")
            return []

    async def get_market_stats(
        self, 
        type_id: int, 
        region_id: int = Region.JITA.value
    ) -> Optional[MarketStats]:
        """获取物品的市场统计信息"""
        sell_orders = await self.get_market_orders(region_id, type_id, OrderType.SELL)
        buy_orders = await self.get_market_orders(region_id, type_id, OrderType.BUY)

        if not sell_orders and not buy_orders:
            return None

        # 计算统计数据
        sell_prices = [order.price for order in sell_orders]
        buy_prices = [order.price for order in buy_orders]
        
        sell_price_min = min(sell_prices) if sell_prices else 0
        buy_price_max = max(buy_prices) if buy_prices else 0
        
        total_volume = sum(order.volume_remain for order in sell_orders + buy_orders)
        
        type_name = await self.get_type_name(type_id)

        return MarketStats(
            type_id=type_id,
            type_name=type_name,
            buy_price_max=buy_price_max,
            sell_price_min=sell_price_min,
            spread=buy_price_max - sell_price_min,
            volume=total_volume,
            orders_count=len(sell_orders) + len(buy_orders),
            updated_at=datetime.now(),
        )

    async def get_type_name(self, type_id: int) -> str:
        """获取物品名称"""
        cache_key = f"type_name_{type_id}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]

        url = f"{self.api_base}/universe/types/{type_id}/"
        
        try:
            session = await self.get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    name = data.get("name", f"Unknown Type {type_id}")
                    self.cache[cache_key] = name
                    return name
        except Exception as e:
            print(f"Error fetching type name: {e}")
        
        return f"Unknown Type {type_id}"

    async def search_type_id(self, name: str) -> List[Tuple[int, str]]:
        """搜索物品ID"""
        # 先检查常用物品
        if name.lower() in self.common_items:
            return [(self.common_items[name.lower()], name.lower())]

        url = f"{self.api_base}/search/"
        params = {
            "categories": "inventory_type",
            "datasource": "tranquility",
            "language": "en",
            "search": name,
            "strict": "false",
        }

        try:
            session = await self.get_session()
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    type_ids = data.get("inventory_type", [])[:5]
                    
                    results = []
                    for type_id in type_ids:
                        type_name = await self.get_type_name(type_id)
                        results.append((type_id, type_name))
                    
                    return results
        except Exception as e:
            print(f"Error searching type: {e}")
        
        return []

    # ==================== Analysis Methods ====================

    async def calculate_hauling_profit(
        self, 
        type_id: int, 
        from_region: int, 
        to_region: int,
        cargo_size: int = 10000
    ) -> Dict:
        """计算跨区域运输利润"""
        # 获取源区域卖出价格
        source_stats = await self.get_market_stats(type_id, from_region)
        # 获取目标区域收购价格
        dest_orders = await self.get_market_orders(to_region, type_id, OrderType.BUY)
        
        if not source_stats or not dest_orders:
            return {"error": "Unable to fetch market data"}

        # 排序目标区域收购订单（价格从高到低）
        dest_orders.sort(key=lambda x: x.price, reverse=True)
        
        # 计算运输量
        total_volume = 0
        total_profit = 0
        volume_per_unit = 0.01  # 默认体积，实际应该查询物品体积
        
        for order in dest_orders:
            if total_volume >= cargo_size:
                break
            
            available_volume = min(order.volume_remain, 
                                 int((cargo_size - total_volume) / volume_per_unit))
            
            if available_volume > 0:
                profit_per_unit = order.price - source_stats.sell_price_min
                profit = profit_per_unit * available_volume
                
                total_volume += available_volume * volume_per_unit
                total_profit += profit

        return {
            "type_name": source_stats.type_name,
            "source_region": from_region,
            "destination_region": to_region,
            "source_price": source_stats.sell_price_min,
            "destination_price": dest_orders[0].price if dest_orders else 0,
            "profit_margin": dest_orders[0].price - source_stats.sell_price_min,
            "total_profit": total_profit,
            "volume_traded": total_volume,
            "profit_percentage": ((dest_orders[0].price - source_stats.sell_price_min) 
                                / source_stats.sell_price_min * 100) if source_stats.sell_price_min > 0 else 0,
        }

    async def market_scanner(
        self, 
        region_id: int, 
        min_margin: float = 10.0
    ) -> List[Dict]:
        """市场扫描器 - 扫描高利润物品"""
        opportunities = []
        
        # 扫描常用矿石和物品
        for item_name, type_id in self.common_items.items():
            stats = await self.get_market_stats(type_id, region_id)
            
            if stats and stats.spread > 0:
                margin_percent = (stats.spread / stats.buy_price_max * 100 
                                if stats.buy_price_max > 0 else 0)
                
                if margin_percent >= min_margin:
                    opportunities.append({
                        "type_name": stats.type_name,
                        "type_id": stats.type_id,
                        "buy_price": stats.buy_price_max,
                        "sell_price": stats.sell_price_min,
                        "spread": stats.spread,
                        "margin_percent": round(margin_percent, 2),
                        "volume": stats.volume,
                    })
        
        # 按利润率排序
        opportunities.sort(key=lambda x: x["margin_percent"], reverse=True)
        return opportunities

    # ==================== Astribot Command Handlers ====================

    async def handle_price_check(self, item_name: str, region: str = "jita") -> str:
        """处理价格查询命令"""
        # 搜索物品
        results = await self.search_type_id(item_name)
        
        if not results:
            return f"❌ 未找到物品: {item_name}"
        
        type_id, type_name = results[0]
        
        # 获取区域ID
        region_id = getattr(Region, region.upper(), Region.JITA).value
        
        # 获取市场统计
        stats = await self.get_market_stats(type_id, region_id)
        
        if not stats:
            return f"❌ 无法获取 {type_name} 的市场数据"
        
        # 格式化输出
        output = f"""
📊 **{stats.type_name}** 市场行情 ({region.upper()})
━━━━━━━━━━━━━━━━━━━━━━━━
💰 最高收购价: {stats.buy_price_max:,.2f} ISK
🏷️ 最低出售价: {stats.sell_price_min:,.2f} ISK
📈 价差: {stats.spread:,.2f} ISK
📦 交易量: {stats.volume:,} 单位
📋 订单数量: {stats.orders_count}
🕐 更新时间: {stats.updated_at.strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━━━━
        """
        return output.strip()

    async def handle_market_scan(self, region: str = "jita", min_margin: float = 10.0) -> str:
        """处理市场扫描命令"""
        region_id = getattr(Region, region.upper(), Region.JITA).value
        opportunities = await self.market_scanner(region_id, min_margin)
        
        if not opportunities:
            return "❌ 未找到符合条件的交易机会"
        
        output = f"""
🔍 **市场扫描结果** ({region.upper()})
━━━━━━━━━━━━━━━━━━━━━━━━
"""
        for i, opp in enumerate(opportunities[:10], 1):
            output += f"""
{i}. {opp['type_name']}
   收购价: {opp['buy_price']:,.2f} ISK
   出售价: {opp['sell_price']:,.2f} ISK
   利润率: {opp['margin_percent']:.1f}%
   交易量: {opp['volume']:,}
"""
        
        output += "━━━━━━━━━━━━━━━━━━━━━━━━"
        return output.strip()

    async def handle_hauling_calc(
        self, 
        item_name: str, 
        from_region: str, 
        to_region: str
    ) -> str:
        """处理运输利润计算"""
        # 搜索物品
        results = await self.search_type_id(item_name)
        if not results:
            return f"❌ 未找到物品: {item_name}"
        
        type_id, type_name = results[0]
        
        # 获取区域ID
        from_id = getattr(Region, from_region.upper(), None)
        to_id = getattr(Region, to_region.upper(), None)
        
        if not from_id or not to_id:
            return "❌ 无效的区域名称"
        
        # 计算利润
        profit_data = await self.calculate_hauling_profit(
            type_id, from_id.value, to_id.value
        )
        
        if "error" in profit_data:
            return f"❌ {profit_data['error']}"
        
        output = f"""
🚚 **运输利润分析**
━━━━━━━━━━━━━━━━━━━━━━━━
📦 物品: {profit_data['type_name']}
🏪 起始区域: {from_region.upper()}
🏢 目标区域: {to_region.upper()}
💰 购买价: {profit_data['source_price']:,.2f} ISK
💎 出售价: {profit_data['destination_price']:,.2f} ISK
📈 单位利润: {profit_data['profit_margin']:,.2f} ISK
📊 利润率: {profit_data['profit_percentage']:.1f}%
━━━━━━━━━━━━━━━━━━━━━━━━
        """
        return output.strip()

    async def handle_item_search(self, item_name: str) -> str:
        """处理物品搜索命令"""
        results = await self.search_type_id(item_name)
        
        if not results:
            return f"❌ 未找到与 '{item_name}' 相关的物品"
        
        output = f"""
🔍 **搜索结果: {item_name}**
━━━━━━━━━━━━━━━━━━━━━━━━
"""
        for i, (type_id, type_name) in enumerate(results[:5], 1):
            output += f"{i}. {type_name} (ID: {type_id})\n"
        
        output += "━━━━━━━━━━━━━━━━━━━━━━━━"
        return output.strip()

    async def cleanup(self):
        """清理资源"""
        if self.session:
            await self.session.close()

# ==================== Plugin Interface for Astribot ====================

class AstribotPlugin:
    """Astribot插件接口"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.market = EVEMarketPlugin()
        
    async def initialize(self):
        """插件初始化"""
        # 注册命令
        await self.bot.register_command("price", self.cmd_price, "查询物品价格")
        await self.bot.register_command("scan", self.cmd_scan, "市场扫描")
        await self.bot.register_command("haul", self.cmd_haul, "运输利润计算")
        await self.bot.register_command("search", self.cmd_search, "搜索物品")
        
        print("✅ EVE Market Plugin initialized")
        
    async def cmd_price(self, message, args):
        """价格查询命令: !price <物品名> [区域]"""
        if not args:
            return "用法: !price <物品名> [区域(jita/amarr/dodixie/rens/hek)]"
        
        parts = args.split()
        item_name = parts[0]
        region = parts[1] if len(parts) > 1 else "jita"
        
        return await self.market.handle_price_check(item_name, region)
    
    async def cmd_scan(self, message, args):
        """市场扫描命令: !scan [区域] [最低利润率]"""
        parts = args.split() if args else []
        region = parts[0] if len(parts) > 0 else "jita"
        min_margin = float(parts[1]) if len(parts) > 1 else 10.0
        
        return await self.market.handle_market_scan(region, min_margin)
    
    async def cmd_haul(self, message, args):
        """运输利润命令: !haul <物品名> <起始区域> <目标区域>"""
        parts = args.split() if args else []
        
        if len(parts) < 3:
            return "用法: !haul <物品名> <起始区域> <目标区域>"
        
        item_name = parts[0]
        from_region = parts[1]
        to_region = parts[2]
        
        return await self.market.handle_hauling_calc(item_name, from_region, to_region)
    
    async def cmd_search(self, message, args):
        """物品搜索命令: !search <物品名>"""
        if not args:
            return "用法: !search <物品名>"
        
        return await self.market.handle_item_search(args)
    
    async def cleanup(self):
        """清理资源"""
        await self.market.cleanup()
        print("✅ EVE Market Plugin cleaned up")

# ==================== Configuration ====================

DEFAULT_CONFIG = {
    "cache_duration_minutes": 5,
    "default_region": "jita",
    "max_orders_per_page": 100,
    "common_items": {
        "tritanium": 34,
        "mexallon": 36,
        "plex": 44992,
    },
    "regions": {
        "jita": 10000002,
        "amarr": 10000043,
        "dodixie": 10000032,
        "rens": 10000030,
        "hek": 10000042,
    }
}

# ==================== Usage Example ====================

async def main():
    """使用示例"""
    # 初始化插件
    market = EVEMarketPlugin()
    
    # 查询Tritanium价格
    result = await market.handle_price_check("tritanium", "jita")
    print(result)
    
    # 市场扫描
    result = await market.handle_market_scan("jita", 15.0)
    print(result)
    
    # 清理
    await market.cleanup()

if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())
