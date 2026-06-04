from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import requests

class market_item:
    def __init__(self, name, sug_price, avg_price):
        self.name = name
        self.sug_price = sug_price
        self.avg_price = avg_price

@register("eveMarket_plugin", "Chillizu", "EVE 市场查询插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.market_data = {}  # 存储市场数据：name -> market_item

    async def initialize(self):
        """初始化时加载市场数据"""
        await self.refresh_data()

    async def refresh_data(self):
        """刷新市场数据"""
        try:
            # 获取所有物品的价格数据
            prices_response = requests.get("https://esi.evetech.net/latest/markets/prices/", headers={
                "Accept-Language": "zh",
                "Accept": "application/json"
            })
            prices_data = prices_response.json()  # list of {"type_id": int, "average_price": float, "adjusted_price": float}

            # 提取type_ids
            type_ids = [item['type_id'] for item in prices_data]

            # 获取名称
            names_response = requests.post("https://esi.evetech.net/latest/universe/names/", json=type_ids, headers={
                "Accept-Language": "zh",
                "Accept": "application/json"
            })
            names_data = names_response.json()  # list of {"id": int, "name": str}

            # 创建name到id的映射
            id_to_name = {entry['id']: entry['name'] for entry in names_data}

            # 创建market_data
            self.market_data = {}
            for item in prices_data:
                tid = item['type_id']
                name = id_to_name.get(tid, f"Unknown Item {tid}")
                self.market_data[name.lower()] = market_item(
                    name=name,
                    sug_price=item.get('adjusted_price', 0),
                    avg_price=item.get('average_price', 0)
                )

            logger.info(f"市场数据刷新完成，共加载 {len(self.market_data)} 个物品")
        except Exception as e:
            logger.error(f"刷新市场数据失败: {e}")

    @filter.command_group("eveMarket")
    def eveMarket(self):
        print("EVE Market Check\n  usage:\n    eveMarket refresh - 刷新市场数据\n    eveMarket check {item_name} - 查询物品价格")

    @eveMarket.command("refresh")
    async def refresh(self, event: AstrMessageEvent):
        """刷新市场信息至缓存"""
        await self.refresh_data()
        yield event.plain_result("市场数据已刷新")

    @eveMarket.command("check")
    async def check(self, event: AstrMessageEvent):
        """查询物品价格"""
        # 获取用户输入的物品名称
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("请提供物品名称，例如：eveMarket check Tritanium")
            return

        item_name = " ".join(args[1:]).lower()
        if item_name in self.market_data:
            item = self.market_data[item_name]
            result = f"物品: {item.name}\n建议价格: {item.sug_price:.2f} ISK\n平均价格: {item.avg_price:.2f} ISK"
            yield event.plain_result(result)
        else:
            # 尝试模糊匹配
            matches = [name for name in self.market_data if item_name in name]
            if matches:
                result = f"未找到 exact 匹配，相似物品:\n" + "\n".join(matches[:5])
                yield event.plain_result(result)
            else:
                yield event.plain_result("未找到该物品，请检查名称")

    async def terminate(self):
        """插件销毁"""
        pass
