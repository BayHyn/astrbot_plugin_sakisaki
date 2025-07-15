import os
import json
import random
import time
import aiohttp
import asyncio
import requests
import http.client
from typing import List
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Plain, BaseMessageComponent
from astrbot.api import logger, AstrBotConfig
from astrbot.api.star import StarTools

# 将这些变量定义在模块顶层，但暂时不赋值
DATA_PATH = None
IMAGE_DEST_PATH = None
IMAGE_URL = "https://raw.githubusercontent.com/oyxning/astrbot_plugin_sakisaki/refs/heads/master/sjp.jpg"

TRIGGER_KEYWORDS = {"saki", "小祥"}

USER_COOLDOWN = {}
RANK_COOLDOWN = {}
RANK_QUERIES = {}

GAME_COOLDOWN_TIME = 60
RANK_COOLDOWN_TIME = 60

# 加载数据
def load_data():
    # 确保 DATA_PATH 已经被初始化
    if not DATA_PATH or not os.path.exists(DATA_PATH):
        return {"play_count": 0, "players": {}}
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"play_count": 0, "players": {}}


# 保存数据
def save_data(data):
    # 确保 DATA_PATH 已经被初始化
    if not DATA_PATH:
        logger.error("DATA_PATH not initialized, cannot save data.")
        return
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def download_image_if_needed():
    # 确保 IMAGE_DEST_PATH 已经被初始化
    if not IMAGE_DEST_PATH:
        logger.error("IMAGE_DEST_PATH not initialized, cannot download image.")
        return
        
    if not os.path.exists(os.path.dirname(IMAGE_DEST_PATH)):
        os.makedirs(os.path.dirname(IMAGE_DEST_PATH), exist_ok=True)
    
    if not os.path.exists(IMAGE_DEST_PATH):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(IMAGE_URL) as resp:
                    if resp.status == 200:
                        with open(IMAGE_DEST_PATH, "wb") as f:
                            f.write(await resp.read())
                        logger.info(f"成功下载图片到 {IMAGE_DEST_PATH}")
                    else:
                        logger.warning(f"下载图片失败，HTTP状态码: {resp.status}")
        except Exception as e:
            logger.warning(f"下载图片出错: {e}")

LAST_TRIGGER_TIME = 0

def clamp(value, min_value=0, max_value=1):
    return max(min(value, max_value), min_value)

@register(
    "astrbot_plugin_sakisaki",
    "LumineStory",
    "香草小祥小游戏插件",
    "1.5.0",
    "https://github.com/oyxning/astrbot_plugin_sakisaki"
)
class SakiSaki(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        
        global DATA_PATH, IMAGE_DEST_PATH
        try:
            data_dir = StarTools.get_data_dir()
            DATA_PATH = os.path.join(data_dir, "sakisaki_data.json")
            IMAGE_DEST_PATH = os.path.join(data_dir, "sjp.jpg")
        except Exception as e:
            logger.error(f"初始化插件路径时出错: {e}")
            if not DATA_PATH:
                DATA_PATH = os.path.join("data", "sakisaki_data.json")
            if not IMAGE_DEST_PATH:
                IMAGE_DEST_PATH = os.path.join("data", "sjp.jpg")


        self.config = config
        self.success_prob = clamp(config.get("success_prob", 0.5), 0, 1)
        self.max_fail_prob = clamp(config.get("max_fail_prob", 0.95), 0, 1)
        self.game_trigger_limit = config.get("game_trigger_limit", 3)
        self.rank_query_limit = config.get("rank_query_limit", 1)

        asyncio.get_event_loop().create_task(download_image_if_needed())

    async def retract_task(self, event: AstrMessageEvent, message_id: int):
        await asyncio.sleep(5)
        try:
            conn = http.client.HTTPConnection("0.0.0.0", 5700)  # 地址和端口请根据你的 CQHTTP 服务实际情况修改
            payload = json.dumps({
                "message_id": message_id
            })
            headers = {
                'Content-Type': 'application/json'
            }
            conn.request("POST", "/delete_msg", payload, headers)
            res = conn.getresponse()
            data = res.read()
            logger.info(f"撤回消息响应: {data.decode('utf-8')}")
            conn.close()
        except Exception as e:
            logger.error(f"撤回消息 {message_id} 失败: {e}")

    async def send_and_retract(self, event: AstrMessageEvent, chain: List[BaseMessageComponent]):
        try:
            sent_info = await event.send(chain)
            message_id = None
            # CQHTTP 可能返回 {"status": "ok", "retcode": 0, "data": {"message_id": 123}}
            if sent_info and isinstance(sent_info, dict):
                data = sent_info.get("data")
                # 兼容 data 为 int（直接 message_id），dict（包含 message_id），None
                if isinstance(data, int):
                    message_id = data if data > 0 else None
                elif isinstance(data, dict):
                    message_id = data.get("message_id")
                    if not message_id or message_id == 0:
                        message_id = None
            if message_id is not None:
                asyncio.create_task(self.retract_task(event, message_id))
            else:
                logger.warning(f"无法从发送响应中获取 message_id: {sent_info}")
        except Exception as e:
            logger.error(f"发送并计划撤回消息失败: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if not isinstance(event, AstrMessageEvent):
            return

        global LAST_TRIGGER_TIME
        current_time = time.time()
        text = event.message_str.lower()

        if "排行" in text or "清除排行" in text:
            return

        if not any(keyword in text for keyword in TRIGGER_KEYWORDS):
            return

        plugin_responses = [
            "🎉 你是追上本祥的第", "😢 你在概率为", "🏆 香草小祥排行榜：",
            "✅ 排行榜已成功清除！", "暂无玩家记录~", "⚠️ 图片未找到，可能下载失败。",
            "⏳ 你的短时追击次数已达上限，请等待", "⏳ 你60s内已经查询过排行榜，请稍后再来查询吧！",
        ]
        if any(response in event.message_str for response in plugin_responses):
            return

        if current_time - LAST_TRIGGER_TIME < 1:
            return
        LAST_TRIGGER_TIME = current_time

        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name()

        if sender_id in USER_COOLDOWN:
            last_trigger_time, trigger_count = USER_COOLDOWN[sender_id]
            elapsed_time = current_time - last_trigger_time
            if elapsed_time < GAME_COOLDOWN_TIME:
                if trigger_count >= self.game_trigger_limit:
                    msg = f"⏳ 你的短时追击次数已达上限，请等待 {round(GAME_COOLDOWN_TIME - elapsed_time)} 秒后再尝试"
                    await self.send_and_retract(event, event.plain_result(msg))
                    return
                else:
                    USER_COOLDOWN[sender_id] = (last_trigger_time, trigger_count + 1)
            else:
                USER_COOLDOWN[sender_id] = (current_time, 1)
        else:
            USER_COOLDOWN[sender_id] = (current_time, 1)

        data = load_data()

        if random.random() < self.success_prob:
            data["play_count"] += 1
            data["players"].setdefault(sender_id, {"name": sender_name, "count": 0})
            data["players"][sender_id]["count"] += 1
            save_data(data)

            msg = f"🎉 你是追上本祥的第 {data['play_count']} 位三角初音！根据统计你香草小祥 {data['players'][sender_id]['count']} 次！"
            await self.send_and_retract(event, event.plain_result(msg))

            if os.path.exists(IMAGE_DEST_PATH):
                await self.send_and_retract(event, event.image_result(os.path.abspath(IMAGE_DEST_PATH)))
            else:
                await self.send_and_retract(event, event.plain_result("⚠️ 图片未找到，可能下载失败。"))
        else:
            fail_prob = round(random.uniform(self.success_prob, self.max_fail_prob) * 100, 2)
            msg = f"😢 你在概率为 {fail_prob}% 时让小祥逃掉了，正在重新追击……"
            await self.send_and_retract(event, event.plain_result(msg))

    @filter.command("saki排行")
    async def show_rank(self, event: AstrMessageEvent):
        sender_id = event.get_sender_id()
        current_time = time.time()

        if sender_id in RANK_COOLDOWN:
            last_rank_time = RANK_COOLDOWN[sender_id]
            rank_query_count = RANK_QUERIES.get(sender_id, 0)
            elapsed_time = current_time - last_rank_time

            if elapsed_time < RANK_COOLDOWN_TIME:
                if rank_query_count >= self.rank_query_limit:
                    msg = "⏳ 你60s内已经查询过排行榜，请稍后再来查询吧！"
                    await self.send_and_retract(event, event.plain_result(msg))
                    return
                else:
                    RANK_QUERIES[sender_id] = rank_query_count + 1
            else:
                RANK_COOLDOWN[sender_id] = current_time
                RANK_QUERIES[sender_id] = 1
        else:
            RANK_COOLDOWN[sender_id] = current_time
            RANK_QUERIES[sender_id] = 1

        data = load_data()
        players = data.get("players", {})
        if not players:
            await self.send_and_retract(event, event.plain_result("暂无玩家记录~"))
            return

        ranking = sorted(players.items(), key=lambda x: x[1]["count"], reverse=True)
        msg = "🏆 香草小祥排行榜：\n"
        for i, (uid, info) in enumerate(ranking[:10], 1):
            msg += f"{i}. {info['name']} - {info['count']} 次\n"
        await self.send_and_retract(event, event.plain_result(msg))

    @filter.command("saki清除排行")
    async def clear_rank(self, event: AstrMessageEvent):
        if not event.is_admin():
            await self.send_and_retract(event, event.plain_result("⚠️ 只有管理员可以清除排行榜！"))
            return

        data = load_data()
        data["play_count"] = 0
        data["players"] = {}
        save_data(data)

        await self.send_and_retract(event, event.plain_result("✅ 排行榜已成功清除！"))

    async def terminate(self):
        logger.info("插件 astrbot_plugin_sakisaki 被终止。")
