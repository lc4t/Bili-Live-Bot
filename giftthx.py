from bilibili import bilibili
from configloader import ConfigLoader
import random
import bilibiliCilent
from utils import check_room
from statistics import Statistics
from printer import Printer
import time
import datetime
import asyncio
import printer
import login
import utils
from sqlapi import session, Live
import rafflehandler
import websockets
import traceback
import struct
import json
import re
import sys
import queue
from raven import Client


ad = '喜欢叶叶的点个关注~有小礼物的可以喂给叶叶~嘻嘻嘻'
delay_ad = 10
last_danmu = 0
danmu_count = 0

thx_queue = queue.Queue()












async def db_adder(x=1, **kwargs):
    db = session()
    try:
        db.add(Live(
            **kwargs
        ))
        db.commit()
    except:
        db.rollback()
        traceback.print_exc()
        dsn = ConfigLoader().dic_user['other_control']['sentry_dsn']
        client = Client(dsn)
        client.captureException()
    await asyncio.sleep(0.0)



class GiftConnection():
    def __init__(self):
        self.danmuji = None
        self.roomid = 0
        self.areaid = -1

    async def run(self):
        self.roomid = ConfigLoader().dic_user['other_control']['gift_monitor_roomid']
        if not self.roomid:
            print('没写gift房间')
            return
        self.danmuji = GiftMonitorHandler(self.roomid, self.areaid)
        while True:
            print('# 正在启动直播监控弹幕姬')
            time_start = int(utils.CurrentTime())
            connect_results = await self.danmuji.connectServer()
            # print(connect_results)
            if not connect_results:
                continue
            task_main = asyncio.ensure_future(self.danmuji.ReceiveMessageLoop())
            task_heartbeat = asyncio.ensure_future(self.danmuji.HeartbeatLoop())
            finished, pending = await asyncio.wait([task_main, task_heartbeat], return_when=asyncio.FIRST_COMPLETED)
            print('主弹幕姬异常或主动断开，正在处理剩余信息')
            time_end = int(utils.CurrentTime())
            if not task_heartbeat.done():
                task_heartbeat.cancel()
            task_terminate = asyncio.ensure_future(self.danmuji.close_connection())
            await asyncio.wait(pending)
            await asyncio.wait([task_terminate])
            printer.info(['主弹幕姬退出，剩余任务处理完毕'], True)
            if time_end - time_start < 5:
                dsn = ConfigLoader().dic_user['other_control']['sentry_dsn']
                client = Client(dsn)
                try:
                    raise Exception('网络不稳定，重试中')
                except:
                    client.captureException()

                print('# 当前网络不稳定，为避免频繁不必要尝试，将自动在5秒后重试')
                await asyncio.sleep(5)




class GiftMonitorHandler(bilibiliCilent.BaseDanmu):
    async def handle_danmu(self, dic):
        cmd = dic['cmd']
        if cmd == 'SEND_GIFT':
            num = dic.get('data').get('num')
            uname = dic.get('data').get('uname')
            uid = dic.get('data').get('uid')
            giftName = dic.get('data').get('giftName')
            coin_type = dic.get('data').get('coin_type')
            gift_id = dic['data']['giftId']
            price = dic.get('data').get('total_coin')
            await db_adder(
                roomid=int(self.roomid),
                cmd=cmd,
                userid=int(uid),
                num=num,
                username=uname,
                giftid=int(gift_id),
                gift=giftName,
                coin_type=coin_type,
                price=price,
            )
            add_thx(uname, num, giftName, self.roomid, coin_type)

        elif cmd == 'DANMU_MSG':
            send_time = dic['info'][0][4]
            author_uid = dic['info'][2][0]
            author_uname = dic['info'][2][1]
            content = dic['info'][1]

            await db_adder(
                roomid=int(self.roomid),
                cmd=cmd,
                time=datetime.datetime.fromtimestamp(int(send_time)),
                userid=author_uid,
                username=author_uname,
                content=content
                )
            try:
                # print('DanMuMsgHandle')
                loop = asyncio.get_event_loop()
                asyncio.run_coroutine_threadsafe(DanMuMsgHandle(dic), loop)
                # print('DanMuMsgHandle done')
            except:
                dsn = ConfigLoader().dic_user['other_control']['sentry_dsn']
                client = Client(dsn)
                client.captureException()
                traceback.print_exc()
        elif cmd == 'GUARD_BUY':
            uname = dic['data']['username']
            uid = dic['data']['uid']
            item = dic['data']['gift_name']
            try:
                gift_id = dic['data']['gift_id'] if dic['data'].get('giftId') is None else dic['data']['giftId']
            except:
                dsn = ConfigLoader().dic_user['other_control']['sentry_dsn']
                client = Client(dsn)
                client.captureException()
                traceback.print_exc()
                gift_id = -1
            price = dic['data']['price']
            num = dic['data']['num']
            msg = '普天同庆! [%s]开通了[%s] 哇哇哇~' % (uname, item)


            await db_adder(
                roomid=int(self.roomid),
                cmd=cmd,
                userid=int(uid),
                username=uname,
                giftid=int(gift_id),
                gift=item,
                num=num,
                coin_type='gold',
                price=price)

            await thx_danmu(msg, self.roomid)
        elif cmd in ['PREPARING', 'RAFFLE_END', 'PK_PROCESS', 'GUARD_LOTTERY_START', 'NOTICE_MSG', 'SYS_GIFT', 'SPECIAL_GIFT', 'ENTRY_EFFECT', 'SYS_MSG', 'GUARD_MSG', 'ENTRY_EFFECT', 'COMBO_SEND', 'COMBO_END', 'ROOM_RANK']:
            pass
            # return
        elif cmd in ['WELCOME_GUARD', 'WELCOME']:
            username = dic['data']['uname'] if cmd =='WELCOME' else dic['data']['username']
            await db_adder(
                roomid=int(self.roomid),
                cmd=cmd,
                userid=dic['data']['uid'],
                username=username,
            )


        elif cmd in ['WISH_BOTTLE']:
            await db_adder(
                roomid=int(self.roomid),
                cmd=cmd,
                userid=0,
                username=cmd,
                content=json.dumps(dic['data'],ensure_ascii=False)
            )
        elif cmd in ['LIVE']:
            msg = '机智的迪迪机好像发现了什么了不得的东西~'
            await thx_danmu(msg, self.roomid)

        else:
            open('other.log', 'a').write(json.dumps(dic) + '\n')
        # print('danmuraffle done')

            # Printer().print_danmu(dic)









async def DanMuMsgHandle(dic):
    # print(dic)

    data_list = json.loads(open('data.json', 'r').read())
    pattern_black_list = data_list.get('block')


    global danmu_count
    global ad
    global last_danmu
    cmd = dic['cmd']
    str_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))

    if cmd == 'DANMU_MSG':
        send_time = dic['info'][0][4]
        send_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(send_time))
        author_uid = dic['info'][2][0]
        author_uname = dic['info'][2][1]
        try:
            roomid = dic['info'][3][3]  # str
        except:
            roomid = ConfigLoader().dic_user['other_control']['default_monitor_roomid']
        content = dic['info'][1]
        output = f'[{send_time_str}]{author_uname}({author_uid}):{content}'

        print(output)

        if '感谢[' in content or ad == content:
            return

        danmu_count += 1
        if danmu_count > 25 and time.time() - last_danmu > delay_ad:
            danmu_count = 0
            await send_ad(ad)
        last_danmu = time.time()

        for d in pattern_black_list:
            try:
                p = ''
                _ = re.findall(d['pattern'], content)
                for x in range(100):
                    if len(_) == 0:
                        break
                    p = _[0]
                    print(p)
                    if type(p) == type(''):
                        break
                    _ = p
                p = len(p)
                l = len(content)
                if p / l >= d['percent']:
                    print(p/l)
                    block_message = f'block: {author_uname} because {content} {p/l}'
                    response = await bilibili.room_block_user(roomid, 1, author_uname, 720)
                    await thx_danmu('auto block user[%s]' % author_uname)
                    print(response)
                    return
            except:
                traceback.print_exc()
                dsn = ConfigLoader().dic_user['other_control']['sentry_dsn']
                client = Client(dsn)
                client.captureException()

        for key, value in data_list.get('data').items():
            # car : '上车'

            check = data_list.get(key)  # 匹配序列
            for d in check:
                # try:
                p = ''
                _ = re.findall(d['pattern'], content)
                for x in range(100):
                    if len(_) == 0:
                        break
                    p = _[0]
                    print(p)
                    if type(p) == type(''):
                        break
                    _ = p
                p = len(p)
                l = len(content)
                if p / l >= d['percent']:
                    print(p/l)
                    print(value)
                    await thx_danmu(value)
                    return
        return

async def send_ad(ad):
    await asyncio.sleep(5)
    await thx_danmu(ad)



def add_thx(uname, num, giftName, roomid, coin_type):
    global thx_queue

    dic = {
        't': time.time(),
        'num': num,
        'uname': uname,
        'giftName': giftName,
        'roomid': roomid,
        'coin_type': coin_type,
    }
    thx_queue.put(dic)


async def run():
    global thx_queue
    food = ['迪迪', '晨晨', '蓝BUFF', '蓝BUFF', '蓝BUFF', '蓝BUFF', '蓝BUFF', '蓝BUFF', '红BUFF', '红BUFF', '红BUFF', '红BUFF', '红BUFF', '河蟹', '野猪', '猎豹', '小鸟', '暴君', '黑暗暴君', '暗影主宰', '刚出生的蜥蜴弟弟', '雄猎豹的女票', '两只魔种小熊', '妲己', '自己的老婆貂蝉QwQ', '叶子', '自己', '小兵']
    eat = [random.choice(['还想吃一个', '偷偷咬了一口', '一口吞下了', '吃掉了峡谷里最后的'])+i for i in food]

    g = ['亿圆', '喵娘', '蓝白胖次', '爱心便当', '闪耀之星', '游戏机', '海带缠潜艇', '盛夏么么茶', '真香', '狂欢之椅', '咸鱼', '给大佬递茶', '炮车', '锄头', '460', '三级头', '鸡小萌', '情书', '辣条', '比心', '小花花', '干杯', '凉了', '冰阔落', 'flag', '金币', '？？？', '吃瓜', 'B坷垃', '喵娘', '打榜', '小金人', '中国队加油', '氪金键盘', '变欧喷雾', '节奏风暴', '666', '233', '友谊的小船', '冰淇淋', '给代打的礼物', '门把手', '你别哭啊', '小光头', '灯塔', '疯狂打call', '粉丝卡', '小电视飞船', '月色真美', '月饼', '南瓜车', '摩天大楼', '礼花']
    want_gift = ['还想吃许多'+i for i in g]

    while(True):
        length = thx_queue.qsize()
        temp_list = []
        filter_list = []
        for i in range(length):
            temp_list.append(thx_queue.get())


        for j in temp_list:

            if len(filter_list) == 0:
                filter_list.append(j)
                continue
            added = False
            for k in range(len(filter_list)):   # 添加重复
                ans = filter_list[k]
                if j.get('uname') == ans.get('uname') and j.get('giftName') == ans.get('giftName') and j.get('roomid') == ans.get('roomid') and j.get('coin_type') == ans.get('coin_type'):
                    filter_list[k].update({
                        't': time.time(),
                        'num': ans.get('num') + j.get('num'),
                    })
                    added = True
                    break
            if not added:
                filter_list.append(j)


        for _ in range(len(filter_list)):
            thx_dic = filter_list[_]
            if time.time() - thx_dic['t'] > 5:
                try:
                    if 'lc4t' in thx_dic['uname']:
                        msg = '感谢[吨吨]赠送的%d个%s mua~' % (thx_dic['num'], thx_dic['giftName'])
                    else:
                        msg = '感谢[%s]赠送的%d个%s~' % (thx_dic['uname'], thx_dic['num'], thx_dic['giftName'])
                    if thx_dic['giftName'] == 'B坷垃':
                        msg = '恭喜[%s]喜提叶叶勋章~' % (thx_dic['uname'])
                    if thx_dic['coin_type'] == 'gold':
                        end = random.choice(['说了句还想吃', '说了句没吃饱', '说了句不够吃', '说了句还是饿'] + eat + want_gift)
                        msg = '叶叶吃掉了%s的%d个%s并且' % (thx_dic['uname'], thx_dic['num'], thx_dic['giftName'])
                        msg += '.' * (30-len(msg))
                        msg += end
                except:
                    traceback.print_exc()
                    dsn = ConfigLoader().dic_user['other_control']['sentry_dsn']
                    client = Client(dsn)
                    client.captureException()
                await thx_danmu(msg, thx_dic['roomid'])
            else:
                thx_queue.put(thx_dic)

        await asyncio.sleep(1)


async def thx_danmu(msg, roomid=None):
    loop = asyncio.get_event_loop()

    if roomid is None:
        roomid = ConfigLoader().dic_user['other_control']['gift_monitor_roomid']
    if len(str(roomid)) < 6:
        real_roomid = await check_room(roomid)
    else:
        real_roomid = roomid
    asyncio.run_coroutine_threadsafe(bilibili.request_send_danmu_msg_web(msg, real_roomid), loop)
    # json_response = await bilibili.request_send_danmu_msg_web(msg, real_roomid)
