import os
import json
import random
import time  # 引入时间模块
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Plain
from astrbot.api import logger

DATA_PATH = os.path.join("data", "sakisaki_data.json")
TRIGGER_KEYWORDS = {"saki", "小祥"}

# 新增计时器配置
USER_COOLDOWN = {}  # 存储用户冷却信息
RANK_COOLDOWN = {}  # 存储排行榜冷却信息
RANK_QUERIES = {}   # 存储用户排行榜查询次数

GAME_COOLDOWN_TIME = 60   # 游戏冷却时间（秒）
RANK_COOLDOWN_TIME = 60   # 排行榜冷却时间（秒）

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
    "1.1.0",
    "https://github.com/oyxning/astrbot_plugin_sakisaki"
)
class SakiSaki(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 用户可自行修改以下参数
        self.success_prob = 0.25  # 成功概率，默认25%
        self.max_fail_prob = 0.95  # 失败概率上限，默认95%
        self.game_trigger_limit = 3  # 游戏触发次数限制，默认3次
        self.rank_query_limit = 1   # 排行榜显示次数，默认1次

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        text = event.message_str.lower()
        # 只有在识别到"saki"或"小祥"时才触发事件
        if "saki" in text or "小祥" in text:
            if "排行" in text:
                # 如果识别到"排行"，则调用排行榜命令
                async for msg in self.show_rank(event):
                    yield msg
            else:
                # 否则，触发随机事件
                sender_id = event.get_sender_id()
                sender_name = event.get_sender_name()

                # 检查用户是否在游戏冷却中
                current_time = time.time()
                if sender_id in USER_COOLDOWN:
                    last_trigger_time, trigger_count = USER_COOLDOWN[sender_id]
                    elapsed_time = current_time - last_trigger_time
                    if elapsed_time < GAME_COOLDOWN_TIME:
                        if trigger_count >= self.game_trigger_limit:
                            yield event.plain_result(
                                f"⏳ 你的短时追击次数已达上限，请等待 {round(GAME_COOLDOWN_TIME - elapsed_time)} 秒后再尝试"
                            )
                            return
                        else:
                            # 更新触发次数
                            USER_COOLDOWN[sender_id] = (last_trigger_time, trigger_count + 1)
                    else:
                        # 冷却时间已过，重置计数
                        USER_COOLDOWN[sender_id] = (current_time, 1)
                else:
                    # 首次触发
                    USER_COOLDOWN[sender_id] = (current_time, 1)

                data = load_data()

                if random.random() < self.success_prob:
                    data["play_count"] += 1
                    data["players"].setdefault(sender_id, {"name": sender_name, "count": 0})
                    data["players"][sender_id]["count"] += 1
                    save_data(data)

                    yield event.plain_result(
                        f"🎉 你是追上本祥的第 {data['play_count']} 位三角初音！根据统计你香草小祥 {data['players'][sender_id]['count']} 次！"
                    )
                else:
                    fail_prob = round(random.uniform(self.success_prob, self.max_fail_prob) * 100, 2)
                    yield event.plain_result(
                        f"😢 你在概率为 {fail_prob}% 时让小祥逃掉了，正在重新追击……"
                    )

    @filter.command("saki排行")
    async def show_rank(self, event: AstrMessageEvent):
        sender_id = event.get_sender_id()
        current_time = time.time()

        # 检查用户是否在排行榜冷却中，并统计查询次数
        if sender_id in RANK_COOLDOWN:
            last_rank_time = RANK_COOLDOWN[sender_id]
            rank_query_count = RANK_QUERIES.get(sender_id, 0)
            elapsed_time = current_time - last_rank_time

            if elapsed_time < RANK_COOLDOWN_TIME:
                if rank_query_count >= self.rank_query_limit:
                    yield event.plain_result(
                        f"⏳ 你60s内已经查询过排行榜，请稍后再来查询吧！"
                    )
                    return
                else:
                    # 更新查询次数
                    RANK_QUERIES[sender_id] = rank_query_count + 1
            else:
                # 更新排行榜查询时间和查询次数
                RANK_COOLDOWN[sender_id] = current_time
                RANK_QUERIES[sender_id] = 1
        else:
            # 记录排行榜查询时间和初始化查询次数
            RANK_COOLDOWN[sender_id] = current_time
            RANK_QUERIES[sender_id] = 1

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
