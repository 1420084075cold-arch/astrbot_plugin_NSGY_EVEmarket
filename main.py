from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import requests
from typing import Optional, Tuple, List

@register("helloworld", "YourName", "一个简单的 Hello World 插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""

    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """这是一个 hello world 指令""" # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
        user_name = event.get_sender_name()
        message_str = event.message_str # 用户发的纯文本消息字符串
        message_chain = event.get_messages()# 用户所发的消息的消息链 # from astrbot.api.message_components import *
     #   message_group = event.group_id
        logger.info(message_chain)
        yield event.plain_result(f"Hello, {user_name}, 你发了 {message_str}!") # 发送一条纯文本消息

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""

    # 将方法改为类方法或实例方法，并添加 @staticmethod 装饰器
    @staticmethod
    def get_type_id_by_name_fuzzwork(name: str) -> Optional[int]:
        """
        优先用 fuzzwork 按英文名查询 type_id。
        """
        ESI_BASE = "https://esi.evetech.net/latest"
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
        """
        用 ESI 的 /universe/ids/ 接口，根据名称（可中文）查 type_id。
        ESI 会按你客户端使用的语言返回对应的名字，支持多语言。
        """
        ESI_BASE = "https://esi.evetech.net/latest"
        url = f"{ESI_BASE}/universe/ids/"
        headers = {
            # 可指定语言（目前支持 zh），但这里查 type_id 不影响结果
            "Accept-Language": "zh",
        }
        # /universe/ids/ 需要 POST 一个字符串数组
        resp = requests.post(url, headers=headers, json=[name], timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        # 结构类似:
        # {
        #   "inventory_types": [
        #       {"id": 34, "name": "Tritanium"}
        #   ]
        # }
        inv_types: List[dict] = data.get("inventory_types") or []
        if not inv_types:
            return None

        # 这里默认取第一个匹配的
        return inv_types[0].get("id")

    @staticmethod
    def get_type_id_by_name(name: str) -> Optional[int]:
        """
        综合函数：先尝试英文名（fuzzwork），失败再用 ESI 多语言搜索。
        支持英文或中文名称。
        """
        # 1. 尝试 fuzzwork（英文名）
        type_id = MyPlugin.get_type_id_by_name_fuzzwork(name)
        if type_id:
            return type_id

        # 2. 失败则尝试 ESI 的多语言名称搜索（支持中文）
        type_id = MyPlugin.get_type_id_by_name_esi(name)
        return type_id

    @staticmethod
    def get_jita_price_by_type_id(type_id: int) -> Tuple[Optional[float], Optional[float]]:
        """
        根据 type_id 获取 Jita 的最低卖价和最高买价。
        """
        ESI_BASE = "https://esi.evetech.net/latest"
        REGION_ID_FORGE = 10000002  # The Forge 区域
        SYSTEM_ID_JITA = 30000142  # Jita 星系
        
        page = 1
        sell_prices = []
        buy_prices = []

        while True:
            url = f"{ESI_BASE}/markets/{REGION_ID_FORGE}/orders/"
            params = {
                "order_type": "all",
                "page": page,
                "type_id": type_id,   # 只查这个物品
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            orders = resp.json()

            if not orders:
                break

            for order in orders:
                if order.get("system_id") != SYSTEM_ID_JITA:
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

    @staticmethod
    def get_jita_price_by_name(name: str) -> Tuple[Optional[int], Optional[float], Optional[float]]:
        """
        核心函数：直接用名字查 Jita 价格。
        支持英文和中文名。
        返回 (type_id, min_sell, max_buy)
        """
        type_id = MyPlugin.get_type_id_by_name(name)
        if not type_id:
            return None, None, None

        min_sell, max_buy = MyPlugin.get_jita_price_by_type_id(type_id)
        return type_id, min_sell, max_buy

    @filter.command(".jita")
    async def jita(self, event: AstrMessageEvent, content_message: str):
        item_name = content_message.strip()  # 添加 strip() 去除首尾空格
        type_id, min_sell, max_buy = self.get_jita_price_by_name(item_name)  # 改为 self.
        
        if not type_id:
            yield event.plain_result(f"未找到该物品，请确认名称是否正确。")
        else:
            # 修复：正确缩进这里的代码
            # 注意：不能在 yield 后面直接使用 print，应该使用 logger
            logger.info(f"物品: {item_name} (type_id={type_id})")
            
            if min_sell is None and max_buy is None:
                yield event.plain_result(f"在 Jita 当前没有订单。")
            else:
                # 修复：将两个结果合并为一条消息，或者分别 yield
                sell_text = f"Jita 最低卖价: {min_sell if min_sell is not None else '无'}"
                buy_text = f"Jita 最高买价: {max_buy if max_buy is not None else '无'}"
                yield event.plain_result(f"{sell_text}\n{buy_text}")
