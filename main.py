import os
import json
import random
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Plain
from astrbot.api import logger

# 数据文件保存在 AstrBot 主目录的 /data 路径
DATA_PATH = os.path.join("data", "sakisaki_data.json")
TRIGGER_KEYWORDS = {"saki", "小祥"}

def load_data():
    if not os.path.exists(DATA_PATH):
        return {"play_count": 0, "players": {}}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@register(
    "astrbot_plugin_sakisaki",
    "LumineStory",
    "香草小祥小游戏插件",
    "1.0.0",
    "https://github.com/oyxning/astrbot_plugin_sakisaki"
)
class SakiSaki(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        config = context.get_config()  # ✅ 正确方式读取插件配置
        self.success_prob = config.get("success_prob", 0.25)
        self.max_fail_prob = config.get("max_fail_prob", 0.95)
        self.enable_rank_command = config.get("enable_rank_command", True)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        text = event.message_str.lower()  # ✅ 访问 event 的 message_str
        if not any(keyword in text for keyword in TRIGGER_KEYWORDS):
            return

        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name()
        data = load_data()

        if random.random() < self.success_prob:
            data["play_count"] += 1
            data["players"].setdefault(sender_id, {"name": sender_name, "count": 0})
            data["players"][sender_id]["count"] += 1
            save_data(data)

            yield event.plain_result(
                f"🎉 恭喜，你是本群第 {data['play_count']} 位三角初音！你已经与香草小祥玩耍了 {data['players'][sender_id]['count']} 次！"
            )
        else:
            fail_prob = round(random.uniform(self.success_prob, self.max_fail_prob) * 100, 2)
            yield event.plain_result(
                f"😢 你在概率为 {fail_prob}% 时与小祥失之交臂，正在重新概率运算……"
            )

    @filter.command("saki排行")
    async def show_rank(self, event: AstrMessageEvent):
        if not self.enable_rank_command:
            yield event.plain_result("该群未启用排行榜功能。")
            return

        data = load_data()
        players = data.get("players", {})
        if not players:
            yield event.plain_result("暂无玩家记录~")
            return

        ranking = sorted(players.items(), key=lambda x: x[1]["count"], reverse=True)
        msg = "🏆 香草小祥排行榜：\n"
        for i, (uid, info) in enumerate(ranking[:10], 1):
            msg += f"{i}. {info['name']} - {info['count']} 次\n"
        yield event.plain_result(msg)

    async def terminate(self):
        logger.info("插件 astrbot_plugin_sakisaki 被终止。")
