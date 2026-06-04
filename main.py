from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import requests
from typing import Optional, Tuple, List

@register("helloworld", "YourName", "一个简单的 Hello World 插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    # 定义区域ID常量
    REGION_ID_FORGE = 10000002      # The Forge 区域（Jita所在）
    REGION_ID_PLEX_GLOBAL = 19000001  # PLEX 全球统一市场区域
    SYSTEM_ID_JITA = 30000142       # Jita 星系
    ESI_BASE = "https://esi.evetech.net/latest"

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""

    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """这是一个 hello world 指令"""
        user_name = event.get_sender_name()
        message_str = event.message_str
        message_chain = event.get_messages()
        logger.info(message_chain)
        yield event.plain_result(f"Hello, {user_name}, 你发了 {message_str}!")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""

    @staticmethod
    def get_type_id_by_name_fuzzwork(name: str) -> Optional[int]:
        """优先用 fuzzwork 按英文名查询 type_id。"""
        url = "https://www.fuzzwork.co.uk/api/typeid.php"
        params = {"typename": name}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if isinstance(data, list) and data:
            return data[0].get("typeID")
        elif isinstance(data, dict) and "typeID" in data:
            return data["typeID"]
        return None

    @staticmethod
    def get_type_id_by_name_esi(name: str) -> Optional[int]:
        """用 ESI 的 /universe/ids/ 接口，根据名称（可中文）查 type_id。"""
        ESI_BASE = "https://esi.evetech.net/latest"
        url = f"{ESI_BASE}/universe/ids/"
        headers = {"Accept-Language": "zh"}
        resp = requests.post(url, headers=headers, json=[name], timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        inv_types: List[dict] = data.get("inventory_types") or []
        if not inv_types:
            return None
        return inv_types[0].get("id")

    @staticmethod
    def get_type_id_by_name(name: str) -> Optional[int]:
        """综合函数：先尝试英文名（fuzzwork），失败再用 ESI 多语言搜索。"""
        type_id = MyPlugin.get_type_id_by_name_fuzzwork(name)
        if type_id:
            return type_id
        type_id = MyPlugin.get_type_id_by_name_esi(name)
        return type_id

    def get_jita_price_by_type_id(self, type_id: int, region_id: int = None) -> Tuple[Optional[float], Optional[float]]:
        """
        根据 type_id 获取指定区域的最低卖价和最高买价。
        
        参数:
            type_id: 物品类型ID
            region_id: 区域ID，如果不指定则使用 The Forge (Jita所在区域)
                      对于 PLEX 应使用 19000001 (全球市场)
        """
        # 如果没有指定 region_id，默认使用 The Forge
        if region_id is None:
            region_id = self.REGION_ID_FORGE
        
        # 注意：PLEX 全球市场不需要检查 system_id，因为它是全球统一的
        # 只有 The Forge 区域需要过滤 Jita 星系的订单
        check_system = (region_id == self.REGION_ID_FORGE)
        
        page = 1
        sell_prices = []
        buy_prices = []

        while True:
            url = f"{self.ESI_BASE}/markets/{region_id}/orders/"
            params = {
                "order_type": "all",
                "page": page,
                "type_id": type_id,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            orders = resp.json()

            if not orders:
                break

            for order in orders:
                # 只有 The Forge 区域需要过滤 Jita 星系
                if check_system and order.get("system_id") != self.SYSTEM_ID_JITA:
                    continue

                price = order["price"]
                if order["is_buy_order"]:
                    buy_prices.append(price)
                else:
                    sell_prices.append(price)

            x_pages = resp.headers.get("X-Pages")
            if x_pages is None or page >= int(x_pages):
                break
            page += 1

        min_sell = min(sell_prices) if sell_prices else None
        max_buy = max(buy_prices) if buy_prices else None
        return min_sell, max_buy

    def get_jita_price_by_name(self, name: str, region_id: int = None) -> Tuple[Optional[int], Optional[float], Optional[float]]:
        """
        核心函数：直接用名字查价格。
        支持英文和中文名。
        
        参数:
            name: 物品名称
            region_id: 区域ID，如果不指定则根据物品自动选择
                      对于 PLEX 会自动使用全球市场 ID
        返回:
            (type_id, min_sell, max_buy)
        """
        # 自动判断：如果是 PLEX，使用全球市场区域
        if region_id is None and name.lower() == "plex":
            region_id = self.REGION_ID_PLEX_GLOBAL
            logger.info(f"检测到 PLEX 查询，使用全球市场区域 ID: {region_id}")
        
        type_id = self.get_type_id_by_name(name)
        if not type_id:
            return None, None, None

        min_sell, max_buy = self.get_jita_price_by_type_id(type_id, region_id)
        return type_id, min_sell, max_buy

    @filter.command(".jita")
    async def jita(self, event: AstrMessageEvent, content_message: str):
        """查询 Jita 或全球市场的物品价格"""
        item_name = content_message.strip()
        
        if not item_name:
            yield event.plain_result("请提供物品名称，例如：.jita Tritanium 或 .jita PLEX")
            return
        
        # 查询价格
        type_id, min_sell, max_buy = self.get_jita_price_by_name(item_name)
        
        if not type_id:
            yield event.plain_result(f"未找到物品「{item_name}」，请确认名称是否正确。")
            return
        
        # 判断是 PLEX 还是普通物品，用于显示不同的提示信息
        is_plex = item_name.lower() == "plex"
        
        # 记录日志
        logger.info(f"查询物品: {item_name} (type_id={type_id}, is_plex={is_plex})")
        
        # 构建回复消息
        if min_sell is None and max_buy is None:
            if is_plex:
                yield event.plain_result(f"PLEX 在全球市场当前没有订单，请稍后再试。")
            else:
                yield event.plain_result(f"「{item_name}」在 Jita 当前没有订单。")
        else:
            # 构建价格信息
            result_parts = [f"物品: {item_name}"]
            if is_plex:
                result_parts.append("市场: PLEX 全球统一市场")
            else:
                result_parts.append("市场: Jita (The Forge)")
            
            if min_sell is not None:
                result_parts.append(f"💰 最低卖价: {min_sell:,.2f} ISK")
            else:
                result_parts.append(f"💰 最低卖价: 无")
                
            if max_buy is not None:
                result_parts.append(f"💎 最高买价: {max_buy:,.2f} ISK")
            else:
                result_parts.append(f"💎 最高买价: 无")
            
            # 计算差价（如果有买卖双方价格）
            if min_sell is not None and max_buy is not None and min_sell > max_buy:
                spread = min_sell - max_buy
                spread_percent = (spread / max_buy) * 100
                result_parts.append(f"📊 差价: {spread:,.2f} ISK ({spread_percent:.1f}%)")
            
            yield event.plain_result("\n".join(result_parts))
